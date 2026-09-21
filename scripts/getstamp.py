#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
getstamp.py
Download AllWISE HiPS2FITS stamps for sources.

Inputs (one of):
- --input-csv : CSV with coordinates (ra/dec, RAJ2000/DEJ2000, _RA/_DE; case-insensitive)
- --csvdir    : folder containing SED CSVs named "ra_dec.csv"

Outputs:
- --outdir : folder where PNG stamps are saved (e.g. <runroot>/AllWISE)
- writes a per-source marker: <outdir>/<ra>_<dec>.done  (always written)

Parallel:
- ThreadPoolExecutor (network-bound)
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple, List

import numpy as np
import pandas as pd
from PIL import Image

import astropy.units as u
from astropy.coordinates import Longitude, Latitude, Angle
from astroquery.hips2fits import hips2fits

try:
    from .download_support import report_stats
except ImportError:
    from download_support import report_stats


HIPS_ALLWISE = "CDS/P/AllWISE/color"


def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}

    def pick(cands):
        for c in cands:
            if c in cols:
                return cols[c]
        return None

    ra_col = pick(["ra", "raj2000", "_ra"])
    de_col = pick(["dec", "dej2000", "_de"])

    if ra_col is None or de_col is None:
        raise SystemExit(
            f"[getstamp.py] ERROR: Could not find RA/DEC columns.\n"
            f"Columns: {list(df.columns)}\n"
            f"Accepted: ra/dec, RAJ2000/DEJ2000, _RA/_DE (case-insensitive)"
        )

    df = df.rename(columns={ra_col: "ra", de_col: "dec"})
    df["ra"] = pd.to_numeric(df["ra"], errors="coerce")
    df["dec"] = pd.to_numeric(df["dec"], errors="coerce")
    df = df[df["ra"].notna() & df["dec"].notna()].copy()
    return df


def list_targets(input_csv: Optional[Path], csvdir: Optional[Path]) -> List[Tuple[float, float, str, str]]:
    targets = []
    if input_csv is not None:
        df = normalize_cols(pd.read_csv(input_csv))
        for ra, dec in zip(df["ra"].to_numpy(), df["dec"].to_numpy()):
            ra_str = f"{ra}"
            dec_str = f"{dec}"
            targets.append((float(ra), float(dec), ra_str, dec_str))
        return targets

    if csvdir is None:
        raise SystemExit("[getstamp.py] ERROR: Provide --input-csv or --csvdir")

    for p in sorted(csvdir.glob("*.csv")):
        stem = p.stem  # "ra_dec"
        if "_" not in stem:
            continue
        ra_str, dec_str = stem.split("_", 1)
        try:
            ra = float(ra_str)
            dec = float(dec_str)
        except Exception:
            continue
        targets.append((ra, dec, ra_str, dec_str))
    return targets


def fetch_one(
    ra: float,
    dec: float,
    out_png: Path,
    out_done: Path,
    width: int,
    height: int,
    fov_arcsec: float,
    min_cut: float,
    max_cut: float,
    projection: str,
    retry_rejected: bool = False,
) -> str:
    try:
        if out_png.exists():
            out_done.write_text("OK (cached)\n")
            return "cached"

        if not retry_rejected and out_done.exists():
            # Older releases called this image-quality rejection a download
            # failure. It is a completed request with no usable classifier input.
            if out_done.read_text().strip() in {"FAILED: median test", "REJECTED: median test"}:
                out_done.write_text("REJECTED: median test\n")
                return "rejected"

        result = hips2fits.query(
            hips=HIPS_ALLWISE,
            width=width,
            height=height,
            ra=Longitude(ra * u.deg),
            dec=Latitude(dec * u.deg),
            fov=Angle(fov_arcsec * u.arcsec),
            projection=projection,
            get_query_payload=False,
            format="jpg",
            min_cut=min_cut,
            max_cut=max_cut,
        )

        if result is None:
            out_done.write_text("FAILED: hips2fits returned None\n")
            return "failed"

        # Retain the supplied non-white cutout acceptance test
        med = np.median(result.reshape(-1, 3), axis=0)
        if np.all(med < 250) and np.all(med > 0):
            temporary = out_png.with_suffix(".part")
            Image.fromarray(result.astype("uint8")).save(temporary, format="PNG")
            temporary.replace(out_png)
            out_done.write_text("OK\n")
            return "ok"

        out_done.write_text("REJECTED: median test\n")
        return "rejected"

    except Exception as e:
        out_done.write_text(f"FAILED: {type(e).__name__}: {e}\n")
        return "failed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-csv", default=None, help="CSV with coordinates (preferred for parallel pipeline)")
    ap.add_argument("--csvdir", default=None, help="Fallback: folder with ra_dec.csv SED files")
    ap.add_argument("--outdir", default="myrun/AllWISE", help="Output folder for PNG stamps")
    ap.add_argument("--workers", type=int, default=16, help="Parallel workers")
    ap.add_argument("--width", type=int, default=200)
    ap.add_argument("--height", type=int, default=200)
    ap.add_argument("--fov-arcsec", type=float, default=30.0)
    ap.add_argument("--min-cut", type=float, default=0.5)
    ap.add_argument("--max-cut", type=float, default=99.5)
    ap.add_argument("--projection", default="AIT")
    ap.add_argument(
        "--retry-rejected", action="store_true", help="Request cutouts again after an image-quality rejection"
    )
    args = ap.parse_args()

    input_csv = Path(args.input_csv) if args.input_csv else None
    csvdir = Path(args.csvdir) if args.csvdir else None
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    targets = list(dict.fromkeys(list_targets(input_csv, csvdir)))
    stats = {}

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = []
        for ra, dec, ra_str, dec_str in targets:
            stem = f"{ra_str}_{dec_str}"
            out_png = outdir / f"{stem}.png"
            out_done = outdir / f"{stem}.done"
            futs.append(
                ex.submit(
                    fetch_one,
                    ra,
                    dec,
                    out_png,
                    out_done,
                    args.width,
                    args.height,
                    args.fov_arcsec,
                    args.min_cut,
                    args.max_cut,
                    args.projection,
                    args.retry_rejected,
                )
            )

        # consume futures (quiet; parent process does progress)
        for future in as_completed(futs):
            status = future.result()
            stats[status] = stats.get(status, 0) + 1
    if stats.get("rejected", 0):
        print(
            f"{stats['rejected']} AllWISE cutout(s) rejected by the image-quality check; "
            "these sources remain not_evaluated for AllWISE. Other channels will continue.",
            flush=True,
        )
    report_stats(stats)


if __name__ == "__main__":
    main()
