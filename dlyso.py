#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
dlyso.py
Top-level pipeline runner (expects helper scripts in ./scripts).

Default pipeline (steps="all"):

PARALLEL DOWNLOAD STAGE (runs simultaneously, each with its own progress bar):
A) Download SED CSVs              -> <runroot>/SEDcsv
B) Download AllWISE stamps        -> <runroot>/AllWISE
C) Download ZTF light curves      -> <runroot>/ZTFLC   (public archive)

Each completed representation unlocks its custom and ensemble classifiers.
SED and dust-aware SED share acquisition but render and classify independently.
Inference is serialized to limit GPU memory use; downloads/plots run concurrently.
Results refresh after each completed channel; failed channels do not stop others.

Extra selective mode:
- --steps sed           : ONLY download SED CSVs
- --steps sed_classify  : Download SEDs + make SEDplot+SEDrplot + classify ONLY SED modalities + combine

Other selections:
- --steps all            : everything (default)
- --steps allwise        : ONLY AllWISE stamps
- --steps ztflc          : ONLY ZTF light curves
- --steps downloads      : SED + AllWISE + ZTFLC (parallel)
- --steps plots          : SEDplot + SEDrplot
- --steps dtdm           : DTDM generation only (requires ZTFLC)
- --steps classify       : customclass + class.py (all modalities)
- --steps combine        : final combineresult only

"""

import argparse
import os
import subprocess
import sys
import time
import math
import tempfile
import importlib.metadata
from pathlib import Path
from typing import Optional, List, Dict
from subprocess import Popen

import pandas as pd
import numpy as np

from dlyso_runtime import VERSION, atomic_json, guard_input, model_root, require_models, sha256


VALID_STEPS = (
    "all",
    "sed",
    "sed_classify",
    "allwise",
    "ztflc",
    "downloads",
    "plots",
    "dtdm",
    "classify",
    "combine",
    "preflight",
)


# ---------------- tqdm helpers ----------------
def get_tqdm():
    try:
        from tqdm import tqdm  # type: ignore

        return tqdm
    except Exception:
        return None


def print_step_banner(step_idx: int, total: int, title: str):
    print(f"[{step_idx}/{total}] {title}")


# ---------------- coordinate normalization ----------------
def validate_coordinate_frame(df: pd.DataFrame, input_csv="input"):
    """Return normalized coordinates and the validity mask, without file I/O."""
    reserved = {"_ra_key", "_dec_key", "_input_row", "_rejection_reason"}
    conflicts = [c for c in df.columns if c in reserved or c.startswith(("SEDplot_", "SEDrplot_", "AllWISE_", "DTDM_"))]
    if conflicts:
        raise ValueError(f"Input uses reserved output columns: {', '.join(conflicts)}")
    cols = {c.lower(): c for c in df.columns}

    ra_col = None
    dec_col = None

    for cand in ["ra", "raj2000", "_ra", "ra_icrs", "_ra_icrs"]:
        if cand in cols:
            ra_col = cols[cand]
            break

    for cand in ["dec", "dej2000", "_de", "de_icrs", "_de_icrs"]:
        if cand in cols:
            dec_col = cols[cand]
            break

    if ra_col is None or dec_col is None:
        raise ValueError(
            f"ERROR: Could not find coordinate columns in {input_csv}\n"
            f"Found columns: {list(df.columns)}\n"
            f"Accepted (case-insensitive): ra/dec, RAJ2000/DEJ2000, _RA/_DE"
        )

    df = df.rename(columns={ra_col: "ra", dec_col: "dec"})
    df["ra"] = pd.to_numeric(df["ra"], errors="coerce")
    df["dec"] = pd.to_numeric(df["dec"], errors="coerce")
    valid = (
        np.isfinite(df["ra"])
        & np.isfinite(df["dec"])
        & df["ra"].between(0, 360, inclusive="left")
        & df["dec"].between(-90, 90)
    )
    return df, valid


def normalize_input_coords(input_csv: Path, out_csv: Path) -> Path:
    """
    Normalize coordinate columns to 'ra' and 'dec'.

    Accepted RA names (case-insensitive):  ra, raj2000, _ra
    Accepted DEC names (case-insensitive): dec, dej2000, _de
    """
    try:
        df, valid = validate_coordinate_frame(pd.read_csv(input_csv), input_csv)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    rejected = df.loc[~valid].copy()
    rejected.insert(0, "_input_row", np.flatnonzero(~valid) + 2)
    rejected["_rejection_reason"] = "Coordinates must be finite; 0 <= RA < 360 and -90 <= Dec <= 90 degrees"
    df = df.loc[valid].copy()

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    rejected.to_csv(out_csv.parent / "rejected_rows.csv", index=False)
    df.to_csv(out_csv, index=False)
    return out_csv


# ---------------- subprocess runner ----------------
def run_cmd(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    *,
    title: str = "",
    verbose: bool = False,
) -> None:
    if verbose:
        p = subprocess.run(cmd, env=env)
    else:
        p = subprocess.run(cmd, env=env, capture_output=True, text=True)

    if p.returncode != 0:
        if not verbose:
            if title:
                print(f"\n[ERROR] Step failed: {title}")
            if p.stdout:
                print("\n--- STDOUT ---\n", p.stdout)
            if p.stderr:
                print("\n--- STDERR ---\n", p.stderr)
        raise SystemExit(p.returncode)


def start_proc(cmd: List[str], env: Optional[Dict[str, str]], verbose: bool) -> Popen:
    if verbose:
        return Popen(cmd, env=env)
    # A file cannot fill up like an unread pipe. Retain diagnostics without a
    # background reader, and close it in check_proc after the child exits.
    output = tempfile.TemporaryFile(mode="w+t")
    try:
        process = Popen(cmd, env=env, stdout=output, stderr=subprocess.STDOUT, text=True)
    except BaseException:
        output.close()
        raise
    process._dlyso_output = output
    return process


def check_proc(p: Popen, title: str, verbose: bool) -> None:
    output = getattr(p, "_dlyso_output", None)
    out = ""
    if output is not None:
        output.seek(0)
        out = output.read()
        output.close()
    if p.returncode == 0:
        return
    if verbose:
        raise SystemExit(p.returncode)
    print(f"\n[ERROR] Step failed: {title}")
    if out:
        print("\n--- STDOUT ---\n", out)
    raise SystemExit(p.returncode)


def count_suffix(folder: Path, suffix: str) -> int:
    if not folder.exists():
        return 0
    s = suffix.lower()
    return sum(1 for p in folder.iterdir() if p.is_file() and p.suffix.lower() == s)


def validate_args(args: argparse.Namespace) -> None:
    """Fail fast on invalid inputs before creating outputs or starting network work."""
    input_csv = Path(args.input_csv).expanduser()
    if not input_csv.is_file():
        raise SystemExit(f"ERROR: Input CSV does not exist or is not a file: {input_csv}")
    if args.workers < 1:
        raise SystemExit("ERROR: --workers must be at least 1.")
    if args.dtdm_workers is not None and args.dtdm_workers < 1:
        raise SystemExit("ERROR: --dtdm-workers must be at least 1.")
    if args.custom_batch < 1 or args.class_batch < 1:
        raise SystemExit("ERROR: batch sizes must be at least 1.")
    if not math.isfinite(args.radius) or args.radius <= 0:
        raise SystemExit("ERROR: --radius must be greater than 0 arcsec.")


def write_run_manifest(runroot: Path, args: argparse.Namespace, normalized_csv: Path, n_sources: int) -> None:
    """Record the invocation and runtime context without persisting secrets."""
    manifest = {
        "pipeline": "DLYSO",
        "version": VERSION,
        "input_sha256": sha256(Path(args.input_csv).expanduser()),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "python": sys.version.split()[0],
        "input_csv": str(Path(args.input_csv).expanduser().resolve()),
        "normalized_csv": str(normalized_csv.resolve()),
        "runroot": str(runroot),
        "steps": args.steps,
        "source_count": n_sources,
        "parameters": {
            "radius_arcsec": args.radius,
            "workers": args.workers,
            "dtdm_workers": args.dtdm_workers,
            "custom_batch": args.custom_batch,
            "class_batch": args.class_batch,
        },
    }
    root = Path(__file__).resolve().parent
    manifest["software_sha256"] = {
        str(p.relative_to(root)): sha256(p)
        for p in sorted(
            [
                *root.glob("dlyso*.py"),
                *(root / "scripts").rglob("*.py"),
                *(root / "scripts/yso_custom_models_final/yso_bundle/assets").glob("*.json"),
            ]
        )
    }
    manifest["models_sha256"] = {
        str(p.relative_to(model_root())): sha256(p) for p in sorted(model_root().rglob("*.pt"))
    }
    manifest["dependencies"] = {}
    for name in ("numpy", "pandas", "torch", "torchvision", "astropy", "astroquery", "dustmaps", "PySide6"):
        try:
            manifest["dependencies"][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            manifest["dependencies"][name] = "not installed"
    atomic_json(runroot / "run_manifest.json", manifest)


# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser(description="Run DLYSO pipeline with step selection + progress bars.")
    ap.add_argument("--version", action="version", version=VERSION)
    ap.add_argument("input_csv", help="Input CSV with coords (ra/dec, RAJ2000/DEJ2000, _RA/_DE)")
    ap.add_argument("--runroot", default="myrun", help="Root output folder (default: myrun)")
    ap.add_argument("--steps", default="all", choices=VALID_STEPS, help="Pipeline stage preset (default: all)")

    ap.add_argument("--radius", type=float, default=2.0, help="VizieR SED query radius in arcsec (default: 2.0)")
    ap.add_argument("--workers", type=int, default=16, help="Parallel threads (download/stamps/ztf), default 16")
    ap.add_argument("--dtdm-workers", type=int, default=None)
    ap.add_argument("--custom-batch", type=int, default=128)
    ap.add_argument("--class-batch", type=int, default=128)

    ap.add_argument("--verbose", action="store_true")

    args = ap.parse_args()
    validate_args(args)
    stepsel = args.steps.strip().lower()
    if stepsel == "classify":
        require_models(
            ["SEDplot", "SEDrplot"] if stepsel == "sed_classify" else ["SEDplot", "SEDrplot", "AllWISE", "DTDM"]
        )

    runroot = Path(args.runroot).resolve()
    args.input_csv = str(Path(args.input_csv).expanduser().resolve())
    try:
        guard_input(runroot, Path(args.input_csv), radius_arcsec=args.radius)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if stepsel in {"all", "sed_classify"}:
        from dlyso_engine import PipelineRun
        from dlyso_workflow import build_workflow

        modalities = ["SEDplot", "SEDrplot"]
        if stepsel == "all":
            modalities += ["AllWISE", "DTDM"]
        workflow = build_workflow(Path(args.input_csv), runroot, modalities, args.workers, args.class_batch, True)
        for task in workflow.tasks:
            command = task.command
            if task.title == "Validate input":
                command.extend(
                    [
                        "--radius",
                        str(args.radius),
                        "--custom-batch",
                        str(args.custom_batch),
                        "--class-batch",
                        str(args.class_batch),
                    ]
                )
            elif task.title == "Download SED data":
                command.extend(["--radius", str(args.radius)])
            elif task.title == "Create DTDM images" and args.dtdm_workers is not None:
                command[command.index("--workers") + 1] = str(args.dtdm_workers)
            elif task.inference and "--folders" in command:
                command[command.index("--batch-size") + 1] = str(args.custom_batch)
        runroot.mkdir(parents=True, exist_ok=True)

        def emit(kind, payload):
            if kind == "log":
                print(payload, flush=True)

        run = PipelineRun(workflow, runroot, os.environ, emit)
        try:
            run.run()
        except KeyboardInterrupt:
            run.cancel()
            raise
        if run.state["status"] != "complete":
            raise SystemExit(1)
        return

    scripts = Path(__file__).resolve().parent / "scripts"

    # scripts
    downloader = scripts / "sed_download_parallel.py"
    plotter = scripts / "make_sed_plots.py"
    rplotter = scripts / "make_sed_rplots.py"
    stamper = scripts / "getstamp.py"
    ztfgetter = scripts / "getztflc.py"
    dtdm = scripts / "dtdm.py"
    customclass = scripts / "customclass.py"
    class_script = scripts / "class.py"
    combiner = scripts / "combineresult.py"

    for p in [downloader, plotter, rplotter, stamper, ztfgetter, dtdm, customclass, class_script, combiner]:
        if not p.exists():
            raise SystemExit(f"ERROR: Missing script: {p}")

    # dirs
    csvdir = runroot / "SEDcsv"
    plotdir = runroot / "SEDplot"
    rplotdir = runroot / "SEDrplot"
    wisedir = runroot / "AllWISE"
    ztfdir = runroot / "ZTFLC"
    dtdmdir = runroot / "DTDM"
    customout = runroot / "customClass"
    classout = runroot / "ClassProbs"
    outcsv = runroot / "result.csv"

    for d in [csvdir, plotdir, rplotdir, wisedir, ztfdir, dtdmdir, customout, classout, outcsv.parent]:
        d.mkdir(parents=True, exist_ok=True)

    # normalize input coords
    normalized_csv = runroot / "coords_normalized.csv"
    normalized_csv = normalize_input_coords(Path(args.input_csv), normalized_csv)
    n_total = len(pd.read_csv(normalized_csv))
    if n_total == 0:
        raise SystemExit("ERROR: 0 valid coordinates after normalization.")
    write_run_manifest(runroot, args, normalized_csv, n_total)

    if stepsel == "preflight":
        print(f"Preflight passed: {n_total} valid source(s).")
        print("Normalized input:", normalized_csv)
        print("Run manifest:", runroot / "run_manifest.json")
        return

    tqdm = get_tqdm()
    step_titles = []

    # Step planning
    if stepsel in {"all", "downloads"}:
        step_titles.append("Parallel downloads (SED + AllWISE + ZTFLC)")
    elif stepsel == "sed":
        step_titles.append("Download SED CSVs")
    elif stepsel == "sed_classify":
        step_titles.append("Download SED CSVs")
    elif stepsel == "allwise":
        step_titles.append("Download AllWISE stamps")
    elif stepsel == "ztflc":
        step_titles.append("Download ZTF light curves")

    if stepsel in {"all", "plots", "sed_classify"}:
        step_titles += ["Create SED plots", "Create SEDr plots (dust background)"]

    if stepsel in {"all"}:
        step_titles.append("Create DTDM images")
    elif stepsel == "dtdm":
        step_titles.append("Create DTDM images")

    if stepsel in {"all", "classify"}:
        step_titles += ["Custom classification", "PyTorch ensemble classification"]
    elif stepsel == "sed_classify":
        step_titles += ["Custom classification (SED only)", "PyTorch ensemble classification (SED only)"]

    if stepsel in {"all", "combine", "sed_classify"}:
        step_titles.append("Combine results into final CSV")

    total = max(1, len(step_titles))
    step_idx = 0

    def banner(title: str):
        nonlocal step_idx
        step_idx += 1
        if tqdm is None:
            print_step_banner(step_idx, total, title)
        else:
            print(f"\n==> {title}")

    # ---------- helpers for download bars ----------
    def run_single_download(title: str, proc_cmd: List[str], done_folder: Path, done_suffix: str, env=None):
        banner(title)
        if tqdm is None:
            run_cmd(proc_cmd, env=env, title=title, verbose=args.verbose)
            return

        bar = tqdm(total=n_total, desc=title, position=0, ncols=90)
        p = start_proc(proc_cmd, env=env, verbose=args.verbose)
        last = 0
        try:
            while True:
                done = min(n_total, count_suffix(done_folder, done_suffix))
                bar.update(max(0, done - last))
                last = done
                if p.poll() is not None:
                    break
                time.sleep(0.5)
            check_proc(p, title, args.verbose)
        finally:
            bar.close()

    # ---------- EXECUTION ----------
    # 1) Downloads
    if stepsel in {"all", "downloads"}:
        banner("Parallel downloads (SED + AllWISE + ZTFLC)")
        if tqdm is None:
            # sequential fallback
            run_cmd(
                [
                    sys.executable,
                    str(downloader),
                    str(normalized_csv),
                    "--radius",
                    str(args.radius),
                    "--workers",
                    str(args.workers),
                    "--outdir",
                    str(csvdir),
                ],
                title="Download SED CSVs",
                verbose=args.verbose,
            )

            run_cmd(
                [
                    sys.executable,
                    str(stamper),
                    "--input-csv",
                    str(normalized_csv),
                    "--outdir",
                    str(wisedir),
                    "--workers",
                    str(args.workers),
                ],
                title="Download AllWISE stamps",
                verbose=args.verbose,
            )

            run_cmd(
                [
                    sys.executable,
                    str(ztfgetter),
                    "--input-csv",
                    str(normalized_csv),
                    "--outdir",
                    str(ztfdir),
                    "--workers",
                    str(args.workers),
                ],
                env=None,
                title="Download ZTF light curves",
                verbose=args.verbose,
            )
        else:
            sed_bar = tqdm(total=n_total, desc="SED download", position=0, ncols=90)
            wise_bar = tqdm(total=n_total, desc="AllWISE stamps", position=1, ncols=90)
            ztf_bar = tqdm(total=n_total, desc="ZTF light curves", position=2, ncols=90)

            p_sed = start_proc(
                [
                    sys.executable,
                    str(downloader),
                    str(normalized_csv),
                    "--radius",
                    str(args.radius),
                    "--workers",
                    str(args.workers),
                    "--outdir",
                    str(csvdir),
                ],
                env=None,
                verbose=args.verbose,
            )

            p_wise = start_proc(
                [
                    sys.executable,
                    str(stamper),
                    "--input-csv",
                    str(normalized_csv),
                    "--outdir",
                    str(wisedir),
                    "--workers",
                    str(args.workers),
                ],
                env=None,
                verbose=args.verbose,
            )

            p_ztf = start_proc(
                [
                    sys.executable,
                    str(ztfgetter),
                    "--input-csv",
                    str(normalized_csv),
                    "--outdir",
                    str(ztfdir),
                    "--workers",
                    str(args.workers),
                ],
                env=None,
                verbose=args.verbose,
            )

            last_sed = last_wise = last_ztf = 0
            try:
                while True:
                    sed_done = min(n_total, count_suffix(csvdir, ".csv"))
                    wise_done = min(n_total, count_suffix(wisedir, ".done"))
                    ztf_done = min(n_total, count_suffix(ztfdir, ".done"))

                    sed_bar.update(max(0, sed_done - last_sed))
                    wise_bar.update(max(0, wise_done - last_wise))
                    ztf_bar.update(max(0, ztf_done - last_ztf))

                    last_sed, last_wise, last_ztf = sed_done, wise_done, ztf_done

                    if (p_sed.poll() is not None) and (p_wise.poll() is not None) and (p_ztf.poll() is not None):
                        break
                    time.sleep(0.5)

                check_proc(p_sed, "Download SED CSVs", args.verbose)
                check_proc(p_wise, "Download AllWISE stamps", args.verbose)
                check_proc(p_ztf, "Download ZTF light curves", args.verbose)
            finally:
                sed_bar.close()
                wise_bar.close()
                ztf_bar.close()

    elif stepsel in {"sed", "sed_classify"}:
        run_single_download(
            "Download SED CSVs",
            [
                sys.executable,
                str(downloader),
                str(normalized_csv),
                "--radius",
                str(args.radius),
                "--workers",
                str(args.workers),
                "--outdir",
                str(csvdir),
            ],
            csvdir,
            ".csv",
            env=None,
        )
        if stepsel == "sed":
            print("Done (SED download only).")
            print("SEDcsv:", csvdir)
            return

    elif stepsel == "allwise":
        run_single_download(
            "Download AllWISE stamps",
            [
                sys.executable,
                str(stamper),
                "--input-csv",
                str(normalized_csv),
                "--outdir",
                str(wisedir),
                "--workers",
                str(args.workers),
            ],
            wisedir,
            ".done",
            env=None,
        )
        print("Done (AllWISE only).")
        print("AllWISE:", wisedir)
        return

    elif stepsel == "ztflc":
        run_single_download(
            "Download ZTF light curves",
            [
                sys.executable,
                str(ztfgetter),
                "--input-csv",
                str(normalized_csv),
                "--outdir",
                str(ztfdir),
                "--workers",
                str(args.workers),
            ],
            ztfdir,
            ".done",
            env=None,
        )
        print("Done (ZTFLC only).")
        print("ZTFLC:", ztfdir)
        return

    # 2) Plots (for all/plots/sed_classify)
    if stepsel in {"all", "plots", "sed_classify"}:
        banner("Create SED plots")
        run_cmd(
            [sys.executable, str(plotter), "--csvdir", str(csvdir), "--plotdir", str(plotdir)],
            title="Create SED plots",
            verbose=args.verbose,
        )

        banner("Create SEDr plots (dust background)")
        run_cmd(
            [sys.executable, str(rplotter), "--csvdir", str(csvdir), "--plotdir", str(rplotdir)],
            title="Create SEDr plots",
            verbose=args.verbose,
        )

        if stepsel == "plots":
            print("Done (plots only).")
            return

    # 3) DTDM (only full all, or explicit dtdm)
    if stepsel in {"all", "dtdm"}:
        banner("Create DTDM images")
        cmd = [sys.executable, str(dtdm), "--lcdir", str(ztfdir), "--outdir", str(dtdmdir)]
        if args.dtdm_workers is not None:
            cmd += ["--workers", str(args.dtdm_workers)]
        run_cmd(cmd, title="Create DTDM images", verbose=args.verbose)

        if stepsel == "dtdm":
            print("Done (DTDM only).")
            return

    # 4) Classification
    if stepsel in {"all", "classify"}:
        banner("Custom classification")
        run_cmd(
            [
                sys.executable,
                str(customclass),
                "--runroot",
                str(runroot),
                "--outdir",
                str(customout),
                "--batch-size",
                str(args.custom_batch),
                "--device",
                "auto",
                "--models",
                "rca,resnet",
                "--folders",
                "SEDplot,SEDrplot,AllWISE,DTDM",
            ],
            title="Custom classification",
            verbose=args.verbose,
        )

        banner("PyTorch ensemble classification")
        run_cmd(
            [
                sys.executable,
                str(class_script),
                "--runroot",
                str(runroot),
                "--models-dir",
                str(model_root() / "models"),
                "--outdir",
                str(classout),
                "--types",
                "SEDplot,SEDrplot,DTDM,AllWISE",
                "--device",
                "auto",
                "--batch-size",
                str(args.class_batch),
                "--channels-last",
            ],
            title="PyTorch ensemble classification",
            verbose=args.verbose,
        )

        if stepsel == "classify":
            print("Done (classify only).")
            return

    # Special: SED-only classify path
    if stepsel == "sed_classify":
        banner("Custom classification (SED only)")
        run_cmd(
            [
                sys.executable,
                str(customclass),
                "--runroot",
                str(runroot),
                "--outdir",
                str(customout),
                "--batch-size",
                str(args.custom_batch),
                "--device",
                "auto",
                "--models",
                "rca,resnet",
                "--folders",
                "SEDplot,SEDrplot",
            ],
            title="Custom classification (SED only)",
            verbose=args.verbose,
        )

        banner("PyTorch ensemble classification (SED only)")
        run_cmd(
            [
                sys.executable,
                str(class_script),
                "--runroot",
                str(runroot),
                "--models-dir",
                str(model_root() / "models"),
                "--outdir",
                str(classout),
                "--types",
                "SEDplot,SEDrplot",
                "--device",
                "auto",
                "--batch-size",
                str(args.class_batch),
                "--channels-last",
            ],
            title="PyTorch ensemble classification (SED only)",
            verbose=args.verbose,
        )

        banner("Combine results into final CSV")
        run_cmd(
            [
                sys.executable,
                str(combiner),
                str(normalized_csv),
                "--classprobs",
                str(classout),
                "--customclass",
                str(customout),
                "--outcsv",
                str(outcsv),
                "--modalities",
                "SEDplot,SEDrplot",
            ],
            title="Combine results into final CSV",
            verbose=args.verbose,
        )

        print("Done (sed_classify).")
        print("Final CSV:", outcsv)
        return

    # 5) Combine
    if stepsel in {"all", "combine"}:
        banner("Combine results into final CSV")
        run_cmd(
            [
                sys.executable,
                str(combiner),
                str(normalized_csv),
                "--classprobs",
                str(classout),
                "--customclass",
                str(customout),
                "--outcsv",
                str(outcsv),
            ],
            title="Combine results into final CSV",
            verbose=args.verbose,
        )

        if stepsel == "combine":
            print("Done (combine only).")
            print("Final CSV:", outcsv)
            return

    print("All done.")
    print("Outputs:")
    print("  runroot     :", runroot)
    print("  input (orig):", Path(args.input_csv).resolve())
    print("  input (norm):", normalized_csv.resolve())
    print("  SEDcsv      :", csvdir)
    print("  SEDplot     :", plotdir)
    print("  SEDrplot    :", rplotdir)
    print("  AllWISE     :", wisedir)
    print("  ZTFLC       :", ztfdir)
    print("  DTDM        :", dtdmdir)
    print("  customClass :", customout)
    print("  ClassProbs  :", classout)
    print("  Final CSV   :", outcsv)


if __name__ == "__main__":
    main()
