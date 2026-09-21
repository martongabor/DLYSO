import os
import sys
from unittest.mock import patch

from dlyso_engine import PipelineRun
from dlyso_workflow import Task, Workflow


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
