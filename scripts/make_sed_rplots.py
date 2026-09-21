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
import matplotlib.colors as mcolors

from astropy.constants import c
import astropy.units as u
from astropy.coordinates import SkyCoord

from dustmaps.csfd import CSFDQuery


# Match sedrplot.py
BIN_EDGES = np.logspace(np.log10(0.01), np.log10(2000), 299)
BE = np.logspace(np.log10(0.01), np.log10(2000), 300)

MIN_VAL = 0.01
MAX_VAL = 400
NORM = mcolors.LogNorm(vmin=MIN_VAL, vmax=MAX_VAL)


def parse_radec_from_stem(stem: str):
    ra_str, dec_str = stem.split("_", 1)
    return float(ra_str), float(dec_str), ra_str, dec_str


def make_plot_from_csv(csv_path: Path, out_png: Path, dust_value: float, overwrite: bool = False) -> bool:
    """
    Create one SED+r plot using sedrplot.py-compatible logic.
    """
    if out_png.exists() and not overwrite:
        return False

    try:
        sed = pd.read_csv(csv_path)
    except Exception:
        return False

    if not {"sed_freq", "sed_flux"}.issubset(sed.columns):
        return False

    try:
        frequency = np.array(sed["sed_freq"], dtype=float) * u.GHz
        wavelength = (c / frequency).to(u.micrometer)

        nuflux = np.array(sed["sed_freq"], dtype=float) * 1e-23 * np.array(sed["sed_flux"], dtype=float) * 1e9

        # Match sedrplot.py exactly
        bin_indices = np.digitize(wavelength.value, BIN_EDGES)
        log_wavelengths = np.zeros(300, dtype=float)

        good = np.isfinite(bin_indices) & np.isfinite(nuflux) & (bin_indices >= 0) & (bin_indices < 300)
        if not np.any(good):
            return False

        # IMPORTANT: overwrite, do not sum
        log_wavelengths[bin_indices[good]] = nuflux[good]

        lw = BE[log_wavelengths > 0]
        nf = log_wavelengths[log_wavelengths > 0]

        if len(lw) <= 9:
            return False

        try:
            scaled_value = float(NORM(dust_value))
        except Exception:
            scaled_value = 0.0

        if not np.isfinite(scaled_value):
            scaled_value = 0.0
        scaled_value = max(0.0, min(1.0, scaled_value))

        background_color = (1.0, 0.0, 0.0, scaled_value)

        out_png.parent.mkdir(parents=True, exist_ok=True)

        # Match sedrplot.py plotting style
        px = 256
        dpi = 96
        plt.figure(figsize=(px / dpi, px / dpi), dpi=dpi, facecolor=background_color)
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
    ap = argparse.ArgumentParser(description="Create sedrplot.py-compatible SED+r plots.")
    ap.add_argument("--csvdir", default="myrun/SEDcsv", help="Input folder containing SED CSV files")
    ap.add_argument("--plotdir", default="myrun/SEDrplot", help="Output folder for PNG plots")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing PNG files")
    args = ap.parse_args()

    csvdir = Path(args.csvdir)
    plotdir = Path(args.plotdir)
    plotdir.mkdir(parents=True, exist_ok=True)

    csv_files = sorted(csvdir.glob("*.csv"))
    if not csv_files:
        print(f"[EMPTY] No SED photometry in {csvdir}; sources will remain not_evaluated.")
        return

    # Keep batch dust query for speed
    targets = []
    for csv_path in csv_files:
        out_png = plotdir / f"{csv_path.stem}.png"
        if out_png.exists() and not args.overwrite:
            continue
        try:
            ra, dec, _, _ = parse_radec_from_stem(csv_path.stem)
        except Exception:
            continue
        targets.append((csv_path, out_png, ra, dec))

    if not targets:
        print("Nothing to do (all plots exist).")
        return

    q = CSFDQuery()
    coords = SkyCoord([t[2] for t in targets] * u.deg, [t[3] for t in targets] * u.deg, frame="icrs")
    dust_values = q(coords)

    made = 0
    skipped = 0

    for i, (csv_path, out_png, ra, dec) in enumerate(targets, start=1):
        try:
            txt = csv_path.read_text(encoding="utf-8", errors="ignore")
            if "Source not found" in txt and "sed_freq" not in txt:
                skipped += 1
                continue
        except Exception:
            pass

        ok = make_plot_from_csv(csv_path, out_png, float(dust_values[i - 1]), overwrite=args.overwrite)

        if ok:
            made += 1
        else:
            skipped += 1

        if i % 200 == 0 or i == len(targets):
            print(f"[{i}/{len(targets)}] made={made} skipped={skipped}")

    print("Done.")
    print(f"SEDcsv  : {csvdir.resolve()}")
    print(f"SEDrplot: {plotdir.resolve()}")
    print(f"made={made} skipped={skipped}")


if __name__ == "__main__":
    main()
