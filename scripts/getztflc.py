#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
getztflc.py
Download ZTF light curves from IRSA in parallel.

Inputs (one of):
- --input-csv : CSV with coordinates (ra/dec, RAJ2000/DEJ2000, _RA/_DE; case-insensitive)
- --csvdir    : folder containing SED CSVs named "ra_dec.csv" (fallback)

Outputs:
- --outdir : folder where light curve CSVs are saved:
    <ra>_<dec>_zg.csv, <ra>_<dec>_zr.csv, <ra>_<dec>_zi.csv (when available)
  plus per-source marker:
    <ra>_<dec>.done   (always written)

Access:
- Downloads the default public ZTF collection anonymously.

Parallel:
- ThreadPoolExecutor with bounded HTTPS requests
"""

import argparse
import csv
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple, List

import pandas as pd
from astropy.io.votable import parse_single_table

try:
    from .download_support import download_to, report_stats
except ImportError:
    from download_support import download_to, report_stats


IRSA_POS_URL = "https://irsa.ipac.caltech.edu/cgi-bin/ZTF/nph_light_curves?POS=CIRCLE {ra} {dec} {rad_deg}"
IRSA_ID_URL = "https://irsa.ipac.caltech.edu/cgi-bin/ZTF/nph_light_curves?ID={oid}&BAD_CATFLAGS_MASK=32768"


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
            f"[getztflc.py] ERROR: Could not find RA/DEC columns.\n"
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
        raise SystemExit("[getztflc.py] ERROR: Provide --input-csv or --csvdir")

    for p in sorted(csvdir.glob("*.csv")):
        stem = p.stem
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


def votable_to_csv(vot_path: Path, csv_path: Path) -> pd.DataFrame:
    vot = parse_single_table(str(vot_path))
    data = vot.array.filled()

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(list(data.dtype.names))
        for row in data:
            writer.writerow(list(row))
    return pd.read_csv(csv_path)


def pick_oid(df: pd.DataFrame, filtercode: str) -> int:
    try:
        d = df[df["filtercode"] == filtercode]
        if len(d) == 0:
            return 0
        return int(d["oid"].value_counts().idxmax())
    except Exception:
        return 0


def fetch_one_target(ra: float, dec: float, ra_str: str, dec_str: str, outdir: Path, rad_arcsec: float) -> str:
    stem = f"{ra_str}_{dec_str}"
    done_path = outdir / f"{stem}.done"
    tmpdir = outdir / "_tmp"
    tmpdir.mkdir(parents=True, exist_ok=True)

    # original condition: skip deep south
    if dec <= -30:
        done_path.write_text("SKIP: dec<=-30\n")
        return "skipped"

    try:
        # If already done, skip
        if done_path.exists() and done_path.read_text().strip() in {"OK", "EMPTY"}:
            return "cached"

        print(f"ZTF {stem}: requesting public light curves", flush=True)
        rad_deg = rad_arcsec / 3600.0
        pos_url = IRSA_POS_URL.format(ra=ra_str, dec=dec_str, rad_deg=rad_deg)

        pos_tbl = tmpdir / f"{stem}_pos.tbl"
        pos_csv = tmpdir / f"{stem}_pos.csv"

        download_to(pos_url, pos_tbl)
        df = votable_to_csv(pos_tbl, pos_csv)

        # cleanup tmp votable
        try:
            pos_tbl.unlink(missing_ok=True)
        except Exception:
            pass

        # pick dominant oid per filter
        oids = {
            "zg": pick_oid(df, "zg"),
            "zr": pick_oid(df, "zr"),
            "zi": pick_oid(df, "zi"),
        }

        got_any = False
        for flt, oid in oids.items():
            if oid == 0:
                continue

            out_csv = outdir / f"{stem}_{flt}.csv"
            if out_csv.exists():
                got_any = True
                continue

            id_url = IRSA_ID_URL.format(oid=oid)
            id_tbl = tmpdir / f"{stem}_{flt}.tbl"
            id_csv = tmpdir / f"{stem}_{flt}.csv"

            download_to(id_url, id_tbl)
            _ = votable_to_csv(id_tbl, id_csv)

            try:
                id_tbl.unlink(missing_ok=True)
            except Exception:
                pass

            # move into place
            id_csv.replace(out_csv)
            got_any = True

        if got_any:
            done_path.write_text("OK\n")
            return "ok"

        done_path.write_text("EMPTY\n")
        return "empty"

    except Exception as e:
        detail = f"{type(e).__name__}: {' '.join(str(e).split())}"
        response = getattr(e, "response", None)
        if response is not None:
            try:
                root = ET.fromstring(response.content)
                for info in root.iter():
                    if info.tag.rsplit("}", 1)[-1] == "INFO" and info.get("name") == "QUERY_STATUS":
                        message = " ".join("".join(info.itertext()).split())
                        if message:
                            detail += f"; archive message: {message}"
            except ET.ParseError:
                pass
        done_path.write_text(f"FAILED: {detail}\n")
        print(f"ZTF {stem}: download failed: {detail}", flush=True)
        return "failed"

    finally:
        # Remove per-target temporary files left in outdir/_tmp.
        # Final light-curve CSVs are already moved to outdir before this runs.
        for p in tmpdir.glob(f"{stem}_*"):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-csv", default=None, help="CSV with coordinates (preferred for parallel pipeline)")
    ap.add_argument("--csvdir", default=None, help="Fallback: folder with ra_dec.csv SED files")
    ap.add_argument("--outdir", default="myrun/ZTFLC", help="Output folder for ZTF LC CSVs")
    ap.add_argument("--workers", type=int, default=16, help="Parallel workers")
    ap.add_argument("--rad-arcsec", type=float, default=2.0, help="POS=CIRCLE radius (arcsec), default 2.0")
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
            futs.append(ex.submit(fetch_one_target, ra, dec, ra_str, dec_str, outdir, args.rad_arcsec))
        for future in as_completed(futs):
            status = future.result()
            stats[status] = stats.get(status, 0) + 1
            completed = sum(stats.values())
            print(f"ZTF [{completed}/{len(targets)}]: {status}", flush=True)
    report_stats(stats)


if __name__ == "__main__":
    main()
