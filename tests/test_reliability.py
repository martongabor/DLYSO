"""Regression tests for failure handling and result integrity; no network calls."""

import importlib.util
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from astropy.table import Table

from dlyso import check_proc, normalize_input_coords, start_proc
from dlyso_engine import PipelineRun
from dlyso_workflow import Task, Workflow
from dlyso_runtime import atomic_json, guard_input, sha256
from scripts import getztflc, sed_download_parallel
from scripts.combineresult import count_votes

ROOT = Path(__file__).resolve().parents[1]


def test_rejected_coordinates_are_auditable(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("source_id,ra,dec\na,10,20\nb,inf,0\nc,10,95\nd,-1,0\ne,360,0\n")
    normalize_input_coords(source, tmp_path / "normal.csv")
    assert pd.read_csv(tmp_path / "normal.csv").source_id.tolist() == ["a"]
    rejected = pd.read_csv(tmp_path / "rejected_rows.csv")
    assert rejected._input_row.tolist() == [3, 4, 5, 6]
    assert len(rejected._rejection_reason.unique()) == 1


def test_no_predictions_differ_from_negative_predictions():
    assert pd.isna(count_votes(pd.Series(dtype=float), "SEDplot"))
    assert count_votes(pd.Series({"SEDplot_resnet18": 0.01}), "SEDplot") == 0


def test_combiner_preserves_rows_and_full_missing_schema(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("source_id,ra,dec\na,10,20\nb,30,40\n")
    probs = tmp_path / "probabilities"
    probs.mkdir()
    (probs / "class_SEDplot.csv").write_text("ra,dec,p_yso_resnet18\n10,20,0.9\n")
    output = tmp_path / "result.csv"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/combineresult.py"),
            str(source),
            "--classprobs",
            str(probs),
            "--customclass",
            str(tmp_path / "none"),
            "--modalities",
            "SEDplot",
            "--outcsv",
            str(output),
        ],
        check=True,
        capture_output=True,
    )
    result = pd.read_csv(output)
    assert result.source_id.tolist() == ["a", "b"]
    assert result.SEDplot_n_models.tolist() == [1, 0]
    assert result.SEDplot_status.tolist() == ["partial", "not_evaluated"]
    assert result.SEDplot_votes.iloc[0] == 1
    assert pd.isna(result.SEDplot_votes.iloc[1])
    assert "SEDplot_custom_rca" in result


def test_sed_network_failure_is_retryable(tmp_path):
    output = tmp_path / "10_20.csv"
    table = Table({"sed_freq": [1.0], "sed_flux": [2.0], "sed_filter": ["test"]})
    with patch.object(sed_download_parallel, "fetch_bytes", side_effect=[OSError("offline"), b"dummy"]) as fetch:
        with patch.object(sed_download_parallel.Table, "read", return_value=table):
            assert sed_download_parallel.download_one(10, 20, 2, output) == "download_error"
            assert not output.exists()
            assert sed_download_parallel.download_one(10, 20, 2, output) == "ok"
            assert fetch.call_count == 2
    assert pd.read_csv(output).sed_flux.iloc[0] == 2.0


def test_legacy_sed_placeholder_is_retried(tmp_path):
    output = tmp_path / "10_20.csv"
    output.write_text("Source not found")
    with patch.object(sed_download_parallel, "fetch_bytes", side_effect=OSError("offline")) as fetch:
        assert sed_download_parallel.download_one(10, 20, 2, output) == "download_error"
        fetch.assert_called_once()


def test_ztf_failure_is_summarized_and_retried(tmp_path):
    with patch.object(getztflc, "download_to", side_effect=RuntimeError("internal request details")) as fetch:
        for _ in range(2):
            assert getztflc.fetch_one_target(10, 20, "10", "20", tmp_path, 2) == "failed"
        assert fetch.call_count == 2
    assert (tmp_path / "10_20.done").read_text() == "FAILED: RuntimeError: internal request details\n"


def test_ztf_reports_archive_error_message(tmp_path, capsys):
    import requests

    response = requests.Response()
    response.status_code = 400
    response._content = (
        b'<VOTABLE xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE>'
        b'<INFO name="QUERY_STATUS" value="ERROR">UsageFault: No such node (VOTABLE.RESOURCE)</INFO>'
        b"</RESOURCE></VOTABLE>"
    )
    error = requests.HTTPError("400 Bad Request", response=response)
    with patch.object(getztflc, "download_to", side_effect=error):
        assert getztflc.fetch_one_target(10, 20, "10", "20", tmp_path, 2) == "failed"
    detail = "archive message: UsageFault: No such node (VOTABLE.RESOURCE)"
    assert detail in (tmp_path / "10_20.done").read_text()
    assert detail in capsys.readouterr().out


def test_loud_child_does_not_deadlock():
    process = start_proc([sys.executable, "-c", "print('x' * 2000000)"], None, False)
    try:
        process.wait(timeout=10)
        check_proc(process, "test child", False)
        assert process._dlyso_output.closed
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_resume_rejects_changed_catalogue(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("ra,dec\n1,2\n")
    atomic_json(tmp_path / "run_manifest.json", {"input_sha256": sha256(source)})
    guard_input(tmp_path, source)
    source.write_text("ra,dec\n3,4\n")
    with pytest.raises(ValueError, match="different input"):
        guard_input(tmp_path, source)


def test_engine_drains_output_and_saves_logs(tmp_path):
    command = ("test", [sys.executable, "-c", "print('x' * 100000)"])
    events = []
    run = PipelineRun(Workflow([Task(*command)]), tmp_path, os.environ, lambda *event: events.append(event))
    run.run()
    assert json.loads((tmp_path / "run_state.json").read_text())["status"] == "complete"
    assert "x" * 100000 in (tmp_path / "pipeline.log").read_text()
    assert events[-1][0] == "finished"


def test_engine_cancellation_stops_active_child(tmp_path):
    ready = threading.Event()
    command = ("slow", [sys.executable, "-u", "-c", "import time; print('ready'); time.sleep(60)"])
    run = PipelineRun(
        Workflow([Task(*command)]),
        tmp_path,
        os.environ,
        lambda kind, value: ready.set() if kind == "log" and value == "ready" else None,
    )
    thread = threading.Thread(target=run.run)
    thread.start()
    assert ready.wait(timeout=10)
    run.cancel()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert json.loads((tmp_path / "run_state.json").read_text())["status"] == "cancelled"


def test_engine_branch_failure_preserves_other_branch(tmp_path):
    tasks = [
        Task("fails", [sys.executable, "-c", "raise SystemExit(2)"]),
        Task("healthy", [sys.executable, "-c", "print('success')"]),
        Task("dependent", [sys.executable, "-c", "raise AssertionError"], ("fails",)),
    ]
    run = PipelineRun(Workflow(tasks), tmp_path, os.environ, lambda *args: None)
    run.run()
    assert run.state["status"] == "failed"
    assert run.state["steps"]["healthy"] == "complete"
    assert run.state["steps"]["dependent"] == "blocked"


def test_filename_parser_accepts_scientific_notation():
    spec = importlib.util.spec_from_file_location("ensemble", ROOT / "scripts/class.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.parse_ra_dec_from_name("1e-05_-2e-06.png") == (1e-5, -2e-6)


def test_changed_radius_cannot_reuse_photometry(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("ra,dec\n1,2\n")
    atomic_json(tmp_path / "run_manifest.json", {"input_sha256": sha256(source), "parameters": {"radius_arcsec": 2.0}})
    with pytest.raises(ValueError, match="radius changed"):
        guard_input(tmp_path, source, radius_arcsec=5.0)


def test_reserved_output_columns_rejected(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("ra,dec,SEDplot_votes\n1,2,99\n")
    with pytest.raises(SystemExit, match="reserved"):
        normalize_input_coords(source, tmp_path / "normal.csv")


def test_empty_sed_acquisition_can_finish_without_false_predictions(tmp_path):
    from scripts import make_sed_plots

    csvdir = tmp_path / "SEDcsv"
    csvdir.mkdir()
    with patch.object(sys, "argv", ["make_sed_plots", "--csvdir", str(csvdir), "--plotdir", str(tmp_path / "SEDplot")]):
        make_sed_plots.main()
    assert not list((tmp_path / "SEDplot").glob("*.png"))


def test_public_http_requests_ignore_saved_login_state(monkeypatch):
    import requests
    from scripts.download_support import fetch_bytes

    def unexpected_login(*args, **kwargs):
        pytest.fail("Public requests must not consult saved login settings")

    def respond(session, request, **kwargs):
        assert not session.trust_env
        assert "Authorization" not in request.headers
        assert "Cookie" not in request.headers
        response = requests.Response()
        response.status_code = 200
        response._content = b"public data"
        response.request = request
        return response

    monkeypatch.setattr(requests.sessions, "get_netrc_auth", unexpected_login)
    monkeypatch.setattr(requests.Session, "send", respond)
    assert fetch_bytes("https://irsa.ipac.caltech.edu/example") == b"public data"
