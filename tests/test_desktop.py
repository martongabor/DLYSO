"""Offscreen interaction tests for the desktop's data-dependent behavior."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication
from dlyso_ui import DlysoApp


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(application):
    widget = DlysoApp()
    yield widget
    widget.close()
    widget.deleteLater()
    application.processEvents()


def test_ztf_selection_does_not_add_login_fields(window):
    from PySide6.QtWidgets import QLineEdit

    fields = window.findChildren(QLineEdit)
    window.cards["DTDM"].check.setChecked(True)
    assert "DTDM" in window._selected()
    assert window.findChildren(QLineEdit) == fields
    assert all(field.echoMode() == QLineEdit.EchoMode.Normal for field in fields)


def test_legacy_results_are_honest_in_view_and_export(window, tmp_path):
    pd.DataFrame(
        {
            "source_id": ["a", "b"],
            "ra": [10.0, 20.0],
            "dec": [0.0, 1.0],
            "SEDplot_resnet18": [0.9, None],
            "SEDplot_votes": [1, 0],
        }
    ).to_csv(tmp_path / "result.csv", index=False)
    window.runroot = tmp_path
    window._load_results(tmp_path / "result.csv")
    assert window.metrics["missing"].text() == "1"
    assert pd.isna(window.results.loc[1, "SEDplot_votes"])
    window.search.setText("b")
    assert window.table.model().rowCount() == 1
    assert window.table.model().frame.iloc[0]["Coverage"] == "Not evaluated"
    assert window.source_title.text() == "b"
    assert pd.read_csv(tmp_path / "result.csv").loc[1, "SEDplot_votes"] == 0


def test_input_preview_and_missing_modality(window, tmp_path):
    source = tmp_path / "example.csv"
    source.write_text("source_id,ra,dec\na,1,2\n")
    window.input_edit.setText(str(source))
    window._preview_input()
    assert window.catalogue_preview.model().rowCount() == 1
    window.results = pd.DataFrame({"ra": [1], "dec": [2]})
    window.result_modality.setCurrentIndex(2)
    assert window.table.model().frame.iloc[0]["Coverage"] == "Not evaluated"


def test_sorting_keeps_source_detail_consistent(window, tmp_path):
    from PySide6.QtCore import Qt

    pd.DataFrame(
        {
            "source_id": ["a", "b"],
            "ra": [20.0, 10.0],
            "dec": [0.0, 1.0],
            "SEDplot_resnet18": [0.9, 0.1],
            "SEDplot_votes": [1, 0],
        }
    ).to_csv(tmp_path / "result.csv", index=False)
    window.runroot = tmp_path
    window._load_results(tmp_path / "result.csv")
    window.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
    selected = window.table.selectionModel().selectedRows()[0].row()
    assert window.source_title.text() == window.table.model().frame.iloc[selected]["Source"]
    window.results = pd.DataFrame()
    window._filter_results()
    assert window.source_title.text() == "Source detail"
    assert not window.scores.toPlainText()


def test_incremental_results_can_be_inspected_during_run(window, tmp_path):
    path = tmp_path / "result.csv"
    pd.DataFrame({"ra": [10.0], "dec": [20.0], "SEDplot_resnet18": [0.9]}).to_csv(path, index=False)
    window.runroot = tmp_path
    window.run_button.setEnabled(False)
    window._event("results", str(path))
    assert window.result_button.isEnabled()
    assert not window.run_button.isEnabled()
    assert len(window.results) == 1


def test_one_progress_bar_per_modality_tracks_shared_and_classifier_steps(window, tmp_path):
    from dlyso_workflow import build_workflow
    from PySide6.QtWidgets import QProgressBar

    workflow = build_workflow(tmp_path / "input.csv", tmp_path, ["SEDplot", "SEDrplot", "AllWISE", "DTDM"], 4, 16, True)
    window._build_stages(workflow)
    assert set(window.stage_widgets) == {"SEDplot", "SEDrplot", "AllWISE", "DTDM"}
    assert len(window.stages.findChildren(QProgressBar)) == 4
    window._event("step", ("Validate input", "complete"))
    window._event("step", ("Download SED data", "running"))
    assert window.stage_widgets["SEDplot"][1].text() == "Downloading"
    assert window.stage_widgets["SEDrplot"][1].text() == "Downloading"
    for title in ["Download SED data", "Create SED plots", "Classify SEDplot · custom"]:
        window._event("step", (title, "complete"))
    window._event("step", ("Classify SEDplot · ensemble", "running"))
    bar, status = window.stage_widgets["SEDplot"]
    assert status.text() == "Classifying"
    assert bar.value() < bar.maximum()
    window._event("step", ("Classify SEDplot · ensemble", "complete"))
    assert status.text() == "Complete"
    assert bar.value() == bar.maximum()
    window._event("step", ("Download ZTF light curves", "failed"))
    assert window.stage_widgets["DTDM"][1].text() == "Failed"
    assert status.text() == "Complete"


def test_download_only_modality_and_cancellation_progress(window, tmp_path):
    from dlyso_workflow import build_workflow

    window.runroot = tmp_path
    window._build_stages(build_workflow(tmp_path / "input.csv", tmp_path, ["AllWISE"], 4, 16, False))
    window._event("step", ("Validate input", "complete"))
    window._event("step", ("Download AllWISE stamps", "running"))
    window._event("finished", ("cancelled", "Stopped"))
    bar, state = window.stage_widgets["AllWISE"]
    assert state.text() == "Stopped"
    assert bar.value() < bar.maximum()


def test_documentation_relative_links_and_back_navigation(window):
    from PySide6.QtCore import QUrl

    guide = window.guide
    assert guide.source().isLocalFile()
    assert "Create a project" in guide.toPlainText()
    guide.setSource(QUrl("GITHUB_INSTALL.md"))
    assert "Install the application" in guide.toPlainText()
    assert guide.source().fileName() == "GITHUB_INSTALL.md"
    guide.backward()
    assert "Create a project" in guide.toPlainText()
    assert guide.source().toLocalFile().endswith("/dlyso_assets/USER_GUIDE.md")
