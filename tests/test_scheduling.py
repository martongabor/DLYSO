import os
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from dlyso_engine import PipelineRun
from dlyso_workflow import Task, Workflow, build_workflow
from scripts.download_support import PARTIAL_DOWNLOAD_EXIT, report_stats


@pytest.mark.parametrize("cached_key", ["ok", "cached", "skip_exists"])
def test_download_summary_reports_partial_only_with_completed_targets(cached_key, capsys):
    with pytest.raises(SystemExit) as error:
        report_stats({cached_key: 4, "download_error": 1})
    assert error.value.code == PARTIAL_DOWNLOAD_EXIT
    assert "1 target(s) failed" in capsys.readouterr().out
    with pytest.raises(SystemExit) as error:
        report_stats({"empty": 4, "filtered_empty": 2, "failed": 1})
    assert error.value.code == 1


@pytest.mark.parametrize("modality", ["SEDplot", "AllWISE", "DTDM"])
def test_partial_download_unlocks_classification_and_keeps_missing_rows(tmp_path, modality):
    source = tmp_path / "coords_normalized.csv"
    source.write_text("source_id,ra,dec\nusable,10,20\nfailed,30,40\n")
    probabilities = tmp_path / "ClassProbs"
    probabilities.mkdir()
    download = "from scripts.download_support import report_stats; report_stats({'ok': 1, 'failed': 1})"
    classify = (
        f"from pathlib import Path; Path({str(probabilities / ('class_' + modality + '.csv'))!r})"
        ".write_text('ra,dec,p_yso_resnet18\\n10,20,0.9\\n')"
    )
    tasks = [
        Task("Download", [sys.executable, "-c", download], allow_partial_download=True),
        Task("Plots", [sys.executable, "-c", "pass"], ("Download",)),
        Task("Classify", [sys.executable, "-c", classify], ("Plots",), True, modality),
    ]
    combine = [
        sys.executable, str(Path(__file__).resolve().parents[1] / "scripts/combineresult.py"),
        str(source), "--classprobs", str(probabilities), "--customclass", str(tmp_path / "customClass"),
        "--modalities", modality, "--outcsv", str(tmp_path / "result.csv"),
    ]
    run = PipelineRun(Workflow(tasks, ("Combine results", combine)), tmp_path, os.environ, lambda *e: None)
    run.run()
    assert run.state["status"] == "partial"
    assert run.state["steps"]["Download"] == "partial"
    assert run.state["steps"]["Classify"] == "complete"
    result = pd.read_csv(tmp_path / "result.csv")
    assert result.source_id.tolist() == ["usable", "failed"]
    assert result[f"{modality}_n_models"].tolist() == [1, 0]
    assert result[f"{modality}_votes"].iloc[0] == 1
    assert pd.isna(result[f"{modality}_votes"].iloc[1])
    assert result[f"{modality}_status"].iloc[1] == "not_evaluated"


@pytest.mark.parametrize("code,allowed", [(1, True), (2, True), (PARTIAL_DOWNLOAD_EXIT, False)])
def test_unexpected_download_exit_blocks_dependents(tmp_path, code, allowed):
    tasks = [
        Task("Download", [sys.executable, "-c", f"raise SystemExit({code})"], allow_partial_download=allowed),
        Task("Classify", [sys.executable, "-c", "raise AssertionError"], ("Download",)),
    ]
    run = PipelineRun(Workflow(tasks), tmp_path, os.environ, lambda *e: None)
    run.run()
    assert run.state["status"] == "failed"
    assert run.state["steps"]["Classify"] == "blocked"


def test_only_download_tasks_accept_partial_exit(tmp_path):
    workflow = build_workflow(tmp_path / "input.csv", tmp_path, ["SEDplot", "SEDrplot", "AllWISE", "DTDM"], 4, 16, True)
    for task in workflow.tasks:
        assert task.allow_partial_download == task.title.startswith("Download ")


def test_ready_channel_classifies_while_other_download_waits(tmp_path):
    signal = tmp_path / "classified"
    # The other download can only finish after classification. A global barrier
    # would time out, rather than accidentally passing because of timing.
    download = (
        "import time; from pathlib import Path; "
        f"p=Path({str(signal)!r}); deadline=time.monotonic()+8\n"
        "while not p.exists() and time.monotonic()<deadline: time.sleep(.02)\n"
        "assert p.exists()"
    )
    tasks = [
        Task("slow download", [sys.executable, "-c", download]),
        Task("plots", [sys.executable, "-c", "pass"]),
        Task(
            "classify",
            [sys.executable, "-c", f"from pathlib import Path; Path({str(signal)!r}).touch()"],
            ("plots",),
            True,
            "SEDplot",
        ),
    ]
    events = []
    run = PipelineRun(Workflow(tasks), tmp_path, os.environ, lambda *e: events.append(e))
    run.run()
    assert run.state["status"] == "complete"
    assert events.index(("step", ("classify", "running"))) < events.index(("step", ("slow download", "complete")))


def test_inference_serialized_and_failure_keeps_partial_results(tmp_path):
    lockdir = tmp_path / "gpu"
    code = f"import time; from pathlib import Path; p=Path({str(lockdir)!r}); p.mkdir(); time.sleep(.1); p.rmdir()"
    tasks = [
        Task("first", [sys.executable, "-c", code], inference=True, modality="SEDplot"),
        Task("second", [sys.executable, "-c", code], inference=True, modality="SEDrplot"),
        Task("failed download", [sys.executable, "-c", "raise SystemExit(1)"]),
    ]
    run = PipelineRun(Workflow(tasks, ("Combine results", [])), tmp_path, os.environ, lambda *e: None)
    snapshots = []
    with patch.object(run, "_combine", side_effect=lambda done: snapshots.append(set(done))):
        run.run()
    assert run.state["status"] == "partial"
    assert run.state["steps"]["first"] == run.state["steps"]["second"] == "complete"
    assert snapshots[-1] == {"SEDplot", "SEDrplot"}
    assert {"SEDplot"} in snapshots


def test_combiner_excludes_stale_predictions_from_failed_channels(tmp_path):
    import subprocess
    from pathlib import Path
    import pandas as pd

    source = tmp_path / "input.csv"
    source.write_text("ra,dec\n10,20\n")
    (tmp_path / "class_DTDM.csv").write_text("ra,dec,p_yso_resnet18\n10,20,0.99\n")
    (tmp_path / "class_SEDplot.csv").write_text("ra,dec,p_yso_resnet18\n10,20,0.8\n")
    output = tmp_path / "result.csv"
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts/combineresult.py"),
            str(source),
            "--classprobs",
            str(tmp_path),
            "--customclass",
            str(tmp_path),
            "--modalities",
            "SEDplot,DTDM",
            "--available-modalities",
            "SEDplot",
            "--outcsv",
            str(output),
        ],
        check=True,
        capture_output=True,
    )
    row = pd.read_csv(output).iloc[0]
    assert row.SEDplot_n_models == 1
    assert row.DTDM_n_models == 0
    assert pd.isna(row.DTDM_votes)
    assert not output.with_suffix(".csv.part").exists()


def test_preflight_failure_does_not_publish_old_catalogue(tmp_path):
    tasks = [
        Task("Validate input", [sys.executable, "-c", "raise SystemExit(1)"]),
        Task("plots", [sys.executable, "-c", "pass"], ("Validate input",)),
    ]
    run = PipelineRun(Workflow(tasks, ("Combine results", [])), tmp_path, os.environ, lambda *e: None)
    with patch.object(run, "_combine") as combine:
        run.run()
    combine.assert_not_called()
    assert run.state["status"] == "failed"
    assert run.state["steps"]["plots"] == "blocked"


def test_cli_uses_channel_scheduler_and_preserves_parameters(tmp_path, monkeypatch):
    import dlyso

    source = tmp_path / "input.csv"
    source.write_text("ra,dec\n10,20\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dlyso",
            str(source),
            "--runroot",
            str(tmp_path / "run"),
            "--steps",
            "sed_classify",
            "--radius",
            "3",
            "--custom-batch",
            "2",
            "--class-batch",
            "4",
        ],
    )
    with patch("dlyso_engine.PipelineRun") as runner:
        runner.return_value.state = {"status": "complete"}
        dlyso.main()
    workflow = runner.call_args.args[0]
    for task in workflow.tasks:
        if task.title in {"Validate input", "Download SED data"}:
            assert task.command[task.command.index("--radius") + 1] == "3.0"
        if task.inference:
            assert task.command[task.command.index("--batch-size") + 1] == ("2" if "--folders" in task.command else "4")
    assert {task.modality for task in workflow.tasks if task.modality} == {"SEDplot", "SEDrplot"}
