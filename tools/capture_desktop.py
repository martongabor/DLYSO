#!/usr/bin/env python3
"""Capture current Qt widgets using a completed project with public example data."""

import argparse
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from PySide6.QtWidgets import QApplication
from dlyso_ui import DlysoApp, gui_palette
from dlyso_workflow import build_workflow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True, help="Completed ZTF run of the shipped public catalogue")
    args = parser.parse_args()
    path = args.project.resolve()
    state = json.loads((path / "run_state.json").read_text())
    examples = pd.read_csv(ROOT / "examples/coordinates.csv")
    results = pd.read_csv(path / "result.csv")
    if state["status"] != "complete" or set(results.source_id) != set(examples.source_id):
        raise SystemExit("Use a completed run of the current public example catalogue.")
    for source in examples.itertuples():
        row = results.loc[results.source_id == source.source_id].iloc[0]
        if abs(row.ra - source.ra) > 1e-6 or abs(row.dec - source.dec) > 1e-6:
            raise SystemExit("Example coordinates do not match the completed run.")
    app = QApplication([])
    app.setStyle("Fusion")
    app.setPalette(gui_palette())
    window = DlysoApp()
    window.show()
    window._example()
    window._preview_input()
    window.output_edit.setText("~/DLYSO Projects")
    folder = ROOT / "docs/images"
    folder.mkdir(parents=True, exist_ok=True)
    app.processEvents()
    window.grab().save(str(folder / "project.png"))
    window.resize(1120, 760)
    app.processEvents()
    window.grab().save(str(folder / "project-minimum.png"))
    window.resize(1370, 920)
    window.open_project(path)
    window.result_modality.setCurrentIndex(window.result_modality.findData("DTDM"))
    window._navigate(2)
    app.processEvents()
    window.grab().save(str(folder / "results.png"))
    workflow = build_workflow(ROOT / "examples/coordinates.csv", path, ["DTDM"], 1, 1, True)
    window._build_stages(workflow)
    for title, status in state["steps"].items():
        window._event("step", (title, status))
    window.activity_message.setText("Completed ZTF example run")
    window._navigate(1)
    window.log.verticalScrollBar().setValue(window.log.verticalScrollBar().maximum())
    app.processEvents()
    window.grab().save(str(folder / "activity.png"))
    window.close()
    print(f"Screenshots from {path}: {folder}")


if __name__ == "__main__":
    main()
