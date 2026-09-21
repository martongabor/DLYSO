from argparse import Namespace

import pandas as pd
import pytest

from dlyso import normalize_input_coords, validate_args
from dlyso_ui import build_commands, build_workflow


def test_normalize_coordinates_preserves_extra_columns(tmp_path):
    source = tmp_path / "sources.csv"
    output = tmp_path / "run" / "coords_normalized.csv"
    pd.DataFrame({"RAJ2000": [10.5, "bad"], "DEJ2000": [-2.5, 1], "source_id": ["a", "b"]}).to_csv(source, index=False)

    normalize_input_coords(source, output)

    result = pd.read_csv(output)
    assert result.to_dict("records") == [{"ra": 10.5, "dec": -2.5, "source_id": "a"}]


def test_validate_args_rejects_nonpositive_workers(tmp_path):
    source = tmp_path / "sources.csv"
    source.write_text("ra,dec\n1,2\n", encoding="utf-8")
    args = Namespace(input_csv=str(source), workers=0, dtdm_workers=None, custom_batch=1, class_batch=1, radius=2.0)

    with pytest.raises(SystemExit, match="workers"):
        validate_args(args)


def test_ui_plan_only_builds_selected_modalities(tmp_path):
    plan = build_commands(tmp_path / "input.csv", tmp_path / "run", ["AllWISE"], 4, 32, True)
    titles = [title for title, _ in plan]
    assert titles == [
        "Validate input",
        "Download AllWISE stamps",
        "Run custom classifiers",
        "Run ensemble classifiers",
        "Combine results",
    ]


def test_ui_dtdm_plan_builds_public_download_and_representation(tmp_path):
    plan = build_commands(tmp_path / "input.csv", tmp_path / "run", ["DTDM"], 4, 32, False)
    assert [title for title, _ in plan] == ["Validate input", "Download ZTF light curves", "Create DTDM images"]


def test_ui_workflow_parallelizes_independent_modalities(tmp_path):
    workflow = build_workflow(
        tmp_path / "input.csv", tmp_path / "run", ["SEDplot", "SEDrplot", "AllWISE", "DTDM"], 4, 32, True
    )
    tasks = {task.title: task for task in workflow.tasks}
    assert tasks["Create SED plots"].needs == ("Download SED data",)
    assert tasks["Create dust-aware SED plots"].needs == ("Download SED data",)
    for modality, ready in [
        ("SEDplot", "Create SED plots"),
        ("SEDrplot", "Create dust-aware SED plots"),
        ("AllWISE", "Download AllWISE stamps"),
        ("DTDM", "Create DTDM images"),
    ]:
        custom = tasks[f"Classify {modality} · custom"]
        ensemble = tasks[f"Classify {modality} · ensemble"]
        assert custom.needs == (ready,)
        assert custom.command[custom.command.index("--folders") + 1] == modality
        assert ensemble.needs == (custom.title,)
        assert ensemble.command[ensemble.command.index("--types") + 1] == modality
    assert workflow.combine[0] == "Combine results"
