#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
dtdm.py
Create DTDM RGB images from ZTF light curve CSVs.

Input:
  --lcdir   (default: myrun/ZTFLC)  expects files named:
           <ra>_<dec>_zg.csv, <ra>_<dec>_zr.csv, <ra>_<dec>_zi.csv

Output:
  --outdir  (default: myrun/DTDM)   writes:
           <ra>_<dec>.png

Parallel:
  ProcessPoolExecutor (CPU-heavy pairwise diffs + histograms)

Notes:
- Uses only catflags==0 and non-NaN mags
- Requires at least 5 points per band to compute a histogram; otherwise band is zeros
"""

import argparse
import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image


# --- Bin definitions: kept identical to your script ---
DT_BINS = np.array(
    [
        1 / 86400,
        30 / 86400,
        1 / 1440,
        30 / 1440,
        1 / 24,
        2 / 24,
        3 / 24,
        4 / 24,
        5 / 24,
        6 / 24,
        12 / 12,
        1,
        1.5,
        2,
        2.5,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        19,
        20,
        21,
        22,
        23,
        24,
        25,
        26,
        27,
        28,
        29,
        30,
        35,
        40,
        45,
        50,
        60,
        70,
        80,
        90,
        100,
        150,
        200,
        250,
        300,
        350,
        400,
        500,
        600,
        700,
        800,
        900,
        1000,
        1200,
        1400,
        1600,
        1800,
        2000,
        2500,
        3000,
    ],
    dtype=float,
)

DM_BINS = np.array(
    [
        -10,
        -5.0,
        -4.5,
        -4.0,
        -3.5,
        -3.0,
        -2.9,
        -2.8,
        -2.7,
        -2.6,
        -2.5,
        -2.4,
        -2.3,
        -2.2,
        -2.1,
        -2.0,
        -1.9,
        -1.8,
        -1.7,
        -1.6,
        -1.5,
        -1.4,
        -1.3,
        -1.2,
        -1.0,
        -0.9,
        -0.8,
        -0.7,
        -0.6,
        -0.5,
        -0.4,
        -0.3,
        -0.2,
        -0.1,
        -0.09,
        -0.08,
        -0.07,
        -0.06,
        -0.05,
        -0.04,
        -0.03,
        -0.02,
        -0.01,
        0.01,
        0.02,
        0.03,
        0.04,
        0.05,
        0.06,
        0.07,
        0.08,
        0.09,
        0.1,
        0.2,
        0.3,
        0.4,
        0.5,
        0.6,
        0.7,
        0.8,
        0.9,
        1.0,
        1.1,
        1.2,
        1.3,
        1.4,
        1.5,
        1.6,
        1.7,
        1.8,
        1.9,
        2.0,
        2.1,
        2.2,
        2.3,
        2.4,
        2.5,
        2.6,
        2.7,
        2.8,
        2.9,
        3.0,
        3.5,
        4.0,
        4.5,
        5.0,
        10,
    ],
    dtype=float,
)

FILTERS = ("zg", "zr", "zi")


def _hist_from_lc_csv(path: Path) -> np.ndarray:
    """
    Return 2D histogram array shape (len(DM_BINS)-1, len(DT_BINS)-1) in float.
    Zeros if file missing/invalid/too short.
    """
    hshape = (len(DM_BINS) - 1, len(DT_BINS) - 1)

    if not path.exists():
        return np.zeros(hshape, dtype=float)

    try:
        df = pd.read_csv(path)
    except Exception:
        return np.zeros(hshape, dtype=float)

    # Must have these columns
    if not {"mjd", "mag"}.issubset(df.columns):
        return np.zeros(hshape, dtype=float)

    # Apply your quality cuts
    if "catflags" in df.columns:
        df = df[df["catflags"] == 0]

    df = df.dropna(subset=["mjd", "mag"])
    if len(df) < 5:
        return np.zeros(hshape, dtype=float)

    # Sort by time
    df = df.sort_values(by="mjd").reset_index(drop=True)

    t = df["mjd"].to_numpy(dtype=float)
    m = df["mag"].to_numpy(dtype=float)

    n = len(df)
    # pairwise diffs (upper triangle)
    dt_mat = t[np.newaxis, :] - t[:, np.newaxis]
    dm_mat = m[np.newaxis, :] - m[:, np.newaxis]

    iu = np.triu_indices(n, k=1)
    dt = dt_mat[iu]
    dm = dm_mat[iu]

    h, _, _ = np.histogram2d(dm, dt, bins=[DM_BINS, DT_BINS])
    return h.astype(float)


def _make_one_base(base: str, lcdir: Path, outdir: Path, overwrite: bool) -> str:
    """
    base: "<ra>_<dec>"
    returns status string
    """
    out_png = outdir / f"{base}.png"
    if out_png.exists() and not overwrite:
        return "skip_exists"

    gh = _hist_from_lc_csv(lcdir / f"{base}_zg.csv")
    rh = _hist_from_lc_csv(lcdir / f"{base}_zr.csv")
    ih = _hist_from_lc_csv(lcdir / f"{base}_zi.csv")

    if gh.sum() > 0:
        gh = gh / gh.max() * 255.0
    if rh.sum() > 0:
        rh = rh / rh.max() * 255.0
    if ih.sum() > 0:
        ih = ih / ih.max() * 255.0

    rgb = np.stack((gh, rh, ih), axis=-1)

    if rgb.sum() <= 0:
        return "no_data"

    outdir.mkdir(parents=True, exist_ok=True)
    img = Image.fromarray(rgb.astype(np.uint8), mode="RGB")
    temporary = out_png.with_suffix(".part")
    img.save(temporary, format="PNG")
    temporary.replace(out_png)
    return "ok"


def main():
    ap = argparse.ArgumentParser(description="Create DTDM images from ZTF light curves (parallel).")
    ap.add_argument("--lcdir", default="myrun/ZTFLC", help="Input folder with ZTFLC CSVs")
    ap.add_argument("--outdir", default="myrun/DTDM", help="Output folder for DTDM PNGs")
    ap.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 4) - 1),
        help="Parallel processes (default: cpu_count-1)",
    )
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing PNGs")
    args = ap.parse_args()

    lcdir = Path(args.lcdir)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    files = [p.name for p in lcdir.glob("*.csv")]
    if not files:
        print(f"[EMPTY] No ZTF light curves in {lcdir}; no DTDM images to classify.")
        return

    # base = remove trailing _zg/_zr/_zi.csv
    bases = sorted({re.sub(r"_(zg|zr|zi)\.csv$", "", f) for f in files})

    stats = {"ok": 0, "skip_exists": 0, "no_data": 0, "error": 0}

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_make_one_base, base, lcdir, outdir, args.overwrite) for base in bases]
        for i, fut in enumerate(as_completed(futs), start=1):
            try:
                st = fut.result()
            except Exception:
                st = "error"
            stats[st] = stats.get(st, 0) + 1
            if i % 100 == 0 or i == len(futs):
                print(f"[{i}/{len(futs)}] {stats}")

    print("Done.")
    print("lcdir :", lcdir.resolve())
    print("outdir:", outdir.resolve())
    print("stats:", stats)
    if stats["error"]:
        raise SystemExit("DTDM processing failed for one or more sources; retry after checking the inputs.")


if __name__ == "__main__":
    main()
