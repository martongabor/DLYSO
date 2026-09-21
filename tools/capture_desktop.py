#!/usr/bin/env python3
"""Render actual Qt screens with non-sensitive, explicitly synthetic fixtures."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np
from PySide6.QtWidgets import QApplication
from dlyso_ui import DlysoApp
from dlyso_workflow import build_workflow
from scripts.combineresult import THRESHOLDS
from scripts.make_sed_plots import make_plot_from_csv


def main():
    app = QApplication([])
    app.setStyle("Fusion")
    window = DlysoApp()
    window.show()
    window._example()
    window._preview_input()
    window.output_edit.setText("~/DLYSO Projects")
    folder = ROOT / "docs/images"
    folder.mkdir(parents=True, exist_ok=True)
    app.processEvents()
    window.grab().save(str(folder / "project.png"))
    workflow = build_workflow(ROOT / "examples/coordinates.csv", ROOT / "runs/demo", list(window.cards), 4, 16, True)
    window._build_stages(workflow)
    window._event("step", ("Validate input", "complete"))
    for title in ["Download SED data", "Create SED plots", "Classify SEDplot · custom", "Classify SEDplot · ensemble"]:
        window._event("step", (title, "complete"))
    for title in ["Create dust-aware SED plots", "Download AllWISE stamps", "Download ZTF light curves"]:
        window._event("step", (title, "running"))
    window._navigate(1)
    window.activity_message.setText("Demonstration of modality progress")
    window.footer.setText("Synthetic activity states · no downloads or classification are running.")
    app.processEvents()
    window.grab().save(str(folder / "activity.png"))
    with tempfile.TemporaryDirectory(prefix="dlyso-screenshot-") as tmp:
        path = Path(tmp)
        rows = []
        for i in range(18):
            row = {"source_id": f"DEMO-{i + 1:03d}", "ra": 83.4 + i * 0.02, "dec": -5.8 + i * 0.05}
            votes = 0
            for j, name in enumerate(THRESHOLDS["SEDplot"]):
                score = None if i % 4 == 3 else round(0.15 + ((i * 13 + j * 3) % 80) / 100, 3)
                row[f"SEDplot_{name}"] = score
                votes += int(score is not None and score >= THRESHOLDS["SEDplot"][name])
            row["SEDplot_votes"] = votes if i % 4 != 3 else None
            rows.append(row)
            if i % 4 != 3:
                wavelength = np.geomspace(0.35, 150, 28)
                flux = 2e-11 * (wavelength**-0.4) + 8e-11 * np.exp(-(((np.log10(wavelength) - 0.7) / 0.5) ** 2))
                frequency = 299792.458 / wavelength
                csv_path = path / f"{row['ra']}_{row['dec']}.csv"
                pd.DataFrame({"sed_freq": frequency, "sed_flux": flux / (frequency * 1e-14)}).to_csv(
                    csv_path, index=False
                )
                make_plot_from_csv(csv_path, path / "SEDplot" / f"{csv_path.stem}.png")
        pd.DataFrame(rows).to_csv(path / "result.csv", index=False)
        window.runroot = path
        window._load_results(path / "result.csv")
        window._navigate(2)
        window.project_tag.setText("Demonstration catalogue")
        window.footer.setText("Synthetic demonstration data · these values are not scientific predictions.")
        app.processEvents()
        window.grab().save(str(folder / "results.png"))
        window._navigate(0)
        for card in window.cards.values():
            card.check.setChecked(True)
        window.resize(1120, 760)
        app.processEvents()
        window.grab().save(str(folder / "project-minimum.png"))
    window.close()
    print(f"Screenshots: {folder}")


if __name__ == "__main__":
    main()
