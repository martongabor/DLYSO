#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import io
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord
from astropy import units as u
from astropy.table import Table
from astropy.io import ascii

try:
    from .download_support import fetch_bytes, report_stats
except ImportError:
    from download_support import fetch_bytes, report_stats


# ----------------------------
# Filtering logic (ported + fixed)
# ----------------------------
BAD_TABNAMES = {
    "J/MNRAS/375/1220/ic348",
    "II/371/des_dr2",
    "J/ApJ/836/34/table2",
    "J/ApJ/848/97/sample",
    "II/316/gps6",
    "J/AJ/161/234/table3",
    "II/314/gcs8",
    "I/350/gaiaedr3",
    "V/154/sdss16",
    "J/ApJS/207/10/table5",
    "II/359/vhs_dr4",
    "II/311/wise",
    "I/353/gsc242",
    "II/368/sstsl2",
    "I/337/gaia",
    "I/320/spm4",
    "I/345/gaia2",
    "I/360/syntphot",
    "IV/38/tic",
    "I/305/out",
    "IV/39/tic82",
    "II/319/gcs9",
    "I/340/ucac5",
}

BAD_FILTERS = {"PAN-STARRS/PS1:z", "Gaia:G", "GAIA/GAIA2:G", "GAIA/GAIA2:Grp", "GAIA/GAIA2:Gbp", "HIP:Hp"}


def _has_cols(df: pd.DataFrame, cols) -> bool:
    return all(c in df.columns for c in cols)


def filter_sed(df: pd.DataFrame, incoord: SkyCoord) -> pd.DataFrame:
    """
    Apply the fixed survey/filter selection and positional deduplication rules.
    """
    # Require the key columns; if missing, just return as-is
    if not _has_cols(df, ["sed_flux", "sed_filter", "sed_freq"]):
        return df

    # Keep positive fluxes
    df = df[df["sed_flux"] > 0].copy()

    # Drop unwanted tabnames/filters if column exists
    if "_tabname" in df.columns:
        df = df[~df["_tabname"].isin(BAD_TABNAMES)].copy()

    df = df[~df["sed_filter"].isin(BAD_FILTERS)].copy()

    # WISE provenance pruning (only keep specific tables for W3/W4; for W1/W2 keep unwise)
    if "_tabname" in df.columns:
        df = df.drop(df[(df["sed_filter"] == "WISE:W1") & (df["_tabname"] != "II/363/unwise")].index)
        df = df.drop(df[(df["sed_filter"] == "WISE:W2") & (df["_tabname"] != "II/363/unwise")].index)
        df = df.drop(df[(df["sed_filter"] == "WISE:W3") & (df["_tabname"] != "II/328/allwise")].index)
        df = df.drop(df[(df["sed_filter"] == "WISE:W4") & (df["_tabname"] != "II/328/allwise")].index)

    # Resolve filter duplicates (Johnson vs 2MASS, WISE vs Spitzer)
    def drop_if_both(keep_filter: str, drop_filter: str):
        nonlocal df
        if (df["sed_filter"].eq(keep_filter).any()) and (df["sed_filter"].eq(drop_filter).any()):
            df = df[df["sed_filter"] != drop_filter].copy()

    drop_if_both("2MASS:J", "Johnson:J")
    drop_if_both("2MASS:H", "Johnson:H")
    drop_if_both("2MASS:Ks", "Johnson:K")
    drop_if_both("Spitzer/IRAC:8.0", "WISE:W3")
    drop_if_both("Spitzer/MIPS:24", "WISE:W4")

    # Remove WISE W3/W4 if eflux is NaN (fix: Series-safe NaN check)
    if "sed_eflux" in df.columns:
        w3 = df["sed_filter"].eq("WISE:W3")
        if w3.any() and pd.isna(df.loc[w3, "sed_eflux"]).any():
            df = df[~w3].copy()

        w4 = df["sed_filter"].eq("WISE:W4")
        if w4.any() and pd.isna(df.loc[w4, "sed_eflux"]).any():
            df = df[~w4].copy()

    # Compute separations and prune Gaia3 points far away
    if _has_cols(df, ["_RAJ2000", "_DEJ2000"]):
        coords = SkyCoord(ra=df["_RAJ2000"].to_numpy() * u.deg, dec=df["_DEJ2000"].to_numpy() * u.deg, frame="icrs")
        sep = coords.separation(incoord).to(u.arcsec).value  # arcsec
        df["dist_arcsec"] = sep

        # The retained Gaia matching threshold is 1.0 arcsec.
        # Separations are computed explicitly in arcsec.
        for gfilt in ("GAIA/GAIA3:Gbp", "GAIA/GAIA3:Grp", "GAIA/GAIA3:G"):
            df = df.drop(df[(df["sed_filter"] == gfilt) & (df["dist_arcsec"] > 1.0)].index)

    # De-duplicate same frequency by keeping the closest match
    if "dist_arcsec" in df.columns:
        freq = df["sed_freq"].to_numpy()
        uniq = np.unique(freq)
        if len(freq) > len(uniq):
            keep_rows = []
            for f in uniq:
                w = df[df["sed_freq"] == f]
                # keep min dist row
                keep_rows.append(w.loc[w["dist_arcsec"].idxmin()])
            df = pd.DataFrame(keep_rows)

    # Sort by frequency
    df = df.sort_values(by=["sed_freq"]).reset_index(drop=True)
    return df


# ----------------------------
# Download one target
# ----------------------------
def fetch_sed_table(target: str, radius: float) -> Table:
    """Retry malformed archive responses, including truncated HTTP 200 bodies."""
    endpoint = "https://vizier.cds.unistra.fr/viz-bin/sed?"
    # Equivalent URL encodings avoid repeatedly receiving the same broken cached
    # response. They preserve the coordinate precision and search radius.
    urls = [
        endpoint + f"-c={target}&-c.rs={radius}",
        endpoint + urlencode({"-c": target.replace(",", " "), "-c.rs": radius}),
        endpoint + urlencode({"-c": target, "-c.rs": radius}),
    ]
    for attempt, url in enumerate(urls, start=1):
        data = fetch_bytes(url)  # Transport errors use the HTTP helper's retry policy.
        try:
            table = Table.read(io.BytesIO(data), format="votable")
            required = {"sed_freq", "sed_flux", "sed_filter"}
            if len(table) and not required.issubset(table.colnames):
                raise ValueError("SED response is missing required photometry columns")
            return table
        except (ValueError, OSError) as exc:
            detail = " ".join(str(exc).split())
            print(f"SED {target}: invalid response ({attempt}/3): {type(exc).__name__}: {detail}", flush=True)
            if attempt == 3:
                raise
            time.sleep(2 * attempt)


def download_one(ra_val, dec_val, radius: float, out_csv: Path) -> str:
    """
    Downloads the VizieR SED for one coordinate and saves to out_csv.
    Returns a status string.
    """
    if out_csv.exists():
        try:
            cached = pd.read_csv(out_csv)
            if {"sed_freq", "sed_flux", "sed_filter"}.issubset(cached.columns):
                return "skip_exists"
        except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError):
            pass

    out_csv.parent.mkdir(parents=True, exist_ok=True)

    marker = out_csv.with_suffix(".done")
    temporary = out_csv.with_suffix(".part")

    target = f"{ra_val},{dec_val}"
    try:
        sed_tab = fetch_sed_table(target, radius)
    except Exception as exc:
        detail = f"{type(exc).__name__}: {' '.join(str(exc).split())}"
        marker.write_text(f"FAILED: download: {detail}\n")
        print(f"SED {target}: download failed: {detail}", flush=True)
        return "download_error"

    if len(sed_tab) == 0:
        marker.write_text("EMPTY\n")
        return "empty"

    # Save raw table to CSV
    ascii.write(sed_tab, temporary, format="csv", overwrite=True)

    # Re-read with pandas for your filtering workflow
    try:
        sed_df = pd.read_csv(temporary)
    except Exception as exc:
        detail = f"{type(exc).__name__}: {' '.join(str(exc).split())}"
        marker.write_text(f"FAILED: csv parse: {detail}\n")
        print(f"SED {target}: CSV parsing failed: {detail}", flush=True)
        return "csv_read_error"

    incoord = SkyCoord(ra=float(ra_val) * u.deg, dec=float(dec_val) * u.deg, frame="icrs")
    sed_df = filter_sed(sed_df, incoord)

    # If filtering nuked everything, keep a meaningful file
    if len(sed_df) == 0:
        temporary.unlink(missing_ok=True)
        marker.write_text("EMPTY: after filtering\n")
        return "filtered_empty"

    sed_df.to_csv(temporary, index=False)
    temporary.replace(out_csv)
    marker.write_text("OK\n")
    return "ok"


# ----------------------------
# Main
# ----------------------------
def main():
    warnings.filterwarnings("ignore")

    ap = argparse.ArgumentParser(description="Parallel SED downloader from VizieR for a CSV with ra,dec columns.")
    ap.add_argument("input_csv", help="Input CSV containing columns: ra, dec")
    ap.add_argument("--radius", type=float, default=2.0, help="Search radius in arcsec (VizieR -c.rs)")
    ap.add_argument("--workers", type=int, default=16, help="Number of parallel threads")
    ap.add_argument("--outdir", default="myrun/SEDcsv", help="Output directory (default: myrun/SEDcsv)")
    args = ap.parse_args()

    inpath = Path(args.input_csv)
    outdir = Path(args.outdir)

    df = pd.read_csv(inpath)

    if "ra" not in df.columns or "dec" not in df.columns:
        raise SystemExit("ERROR: input CSV must contain 'ra' and 'dec' columns.")

    # Drop NaNs in ra/dec
    df = df[df["ra"].notna() & df["dec"].notna()].reset_index(drop=True)

    # Parallel download
    futures = []
    stats = {"ok": 0, "skip_exists": 0, "empty": 0, "filtered_empty": 0, "download_error": 0, "csv_read_error": 0}

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, row in df.drop_duplicates(subset=["ra", "dec"]).iterrows():
            ra_val = row["ra"]
            dec_val = row["dec"]
            filename = f"{ra_val}_{dec_val}.csv"
            out_csv = outdir / filename
            futures.append(ex.submit(download_one, ra_val, dec_val, args.radius, out_csv))

        for j, fut in enumerate(as_completed(futures), start=1):
            status = fut.result()
            stats[status] = stats.get(status, 0) + 1
            if j % 50 == 0 or j == len(futures):
                print(f"[{j}/{len(futures)}] {stats}")

    print("Done.")
    print("Final stats:", stats)
    print("Output:", outdir.resolve())
    report_stats(stats)


if __name__ == "__main__":
    main()
