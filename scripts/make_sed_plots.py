#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.style.use("fast")

from astropy.constants import c
import astropy.units as u


# Match sedplot.py exactly
BIN_EDGES = np.logspace(np.log10(0.01), np.log10(2000), 299)
BE = np.logspace(np.log10(0.01), np.log10(2000), 300)


def make_plot_from_csv(csv_path: Path, out_png: Path, overwrite: bool = False) -> bool:
    """
    Create one SED plot using the same logic as sedplot.py.

    Returns True if a plot was created, False otherwise.
    """
    if out_png.exists() and not overwrite:
        return False

    try:
        sed = pd.read_csv(csv_path)
    except Exception:
        return False

    # Require the same columns
    if not {"sed_freq", "sed_flux"}.issubset(sed.columns):
        return False

    try:
        # Keep this close to sedplot.py
        frequency = np.array(sed["sed_freq"], dtype=float) * u.GHz
        wavelength = (c / frequency).to(u.micrometer)

        nuflux = np.array(sed["sed_freq"], dtype=float) * 1e-23 * np.array(sed["sed_flux"], dtype=float) * 1e9

        # Same digitization method as sedplot.py
        bin_indices = np.digitize(wavelength.value, BIN_EDGES)

        # Same vector length
        log_wavelengths = np.zeros(300, dtype=float)

        # Match sedplot.py behavior:
        # overwrite bins instead of summing
        good = np.isfinite(bin_indices) & np.isfinite(nuflux) & (bin_indices >= 0) & (bin_indices < 300)
        if not np.any(good):
            return False

        log_wavelengths[bin_indices[good]] = nuflux[good]

        lw = BE[log_wavelengths > 0]
        nf = log_wavelengths[log_wavelengths > 0]

        if len(lw) <= 9:
            return False

        out_png.parent.mkdir(parents=True, exist_ok=True)

        # Match sedplot.py plotting style as closely as possible
        px = 256
        dpi = 96
        plt.figure(figsize=(px / dpi, px / dpi), dpi=dpi)
        plt.plot(lw, nf, "-", linewidth=3, color="black")
        plt.xscale("log")
        plt.yscale("log")
        plt.xlim([0.01, 2000])
        plt.ylim([1e-15, 1e-6])
        plt.axis("off")
        temporary = out_png.with_suffix(".part")
        plt.savefig(temporary, format="png", bbox_inches="tight", pad_inches=0)
        temporary.replace(out_png)
        plt.close()

        return True

    except Exception as exc:
        plt.close("all")
        raise RuntimeError(f"Could not render {csv_path.name}: {type(exc).__name__}") from exc


def main():
    ap = argparse.ArgumentParser(description="Create SED plots from CSVs using sedplot.py-compatible logic.")
    ap.add_argument("--csvdir", default="myrun/SEDcsv", help="Input folder containing SED CSV files")
    ap.add_argument("--plotdir", default="myrun/SEDplot", help="Output folder for PNG plots")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing PNG files")
    args = ap.parse_args()

    csvdir = Path(args.csvdir)
    plotdir = Path(args.plotdir)
    plotdir.mkdir(parents=True, exist_ok=True)

    csv_files = sorted(csvdir.glob("*.csv"))
    if not csv_files:
        print(f"[EMPTY] No SED photometry in {csvdir}; sources will remain not_evaluated.")
        return

    made = 0
    skipped = 0

    for i, csv_path in enumerate(csv_files, start=1):
        out_png = plotdir / f"{csv_path.stem}.png"
        ok = make_plot_from_csv(csv_path, out_png, overwrite=args.overwrite)

        if ok:
            made += 1
        else:
            skipped += 1

        if i % 200 == 0 or i == len(csv_files):
            print(f"[{i}/{len(csv_files)}] made={made} skipped={skipped}")

    print("Done.")
    print(f"SEDcsv:  {csvdir.resolve()}")
    print(f"SEDplot: {plotdir.resolve()}")
    print(f"made={made} skipped={skipped}")


if __name__ == "__main__":
    main()
