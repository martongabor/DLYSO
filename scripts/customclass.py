#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dlyso_runtime import model_root


MODELS_DEFAULT = ("rca", "resnet")

# Canonical product identifiers exported by the bundled inference package.
PRODUCT_CANDIDATES = {
    "SEDplot": ["sed"],
    "SEDrplot": ["sedr"],
    "AllWISE": ["allwise"],
    "DTDM": ["dtdm"],
}


def detect_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def run_demo_infer(
    demo_infer: Path,
    data_folder: Path,
    out_csv: Path,
    product: str,
    model: str,
    device: str,
    batch_size: int,
) -> int:
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(demo_infer),
        "--split",
        str(data_folder),
        "--product",
        product,
        "--model",
        model,
        "--thr",
        "0.0",  # write probabilities for everything
        "--batch_size",
        str(batch_size),
        "--device",
        device,
        "--out_csv",
        str(out_csv),
    ]

    print("\n>>", " ".join(cmd))
    return subprocess.run(cmd, env={**os.environ, "DLYSO_MODEL_ROOT": str(model_root())}).returncode


def main():
    ap = argparse.ArgumentParser(description="Run yso_custom_models_final/demo_infer.py on multiple modalities.")
    ap.add_argument("--runroot", default="myrun", help="Root folder containing SEDplot/SEDrplot/AllWISE/DTDM")
    ap.add_argument("--outdir", default="myrun/customClass", help="Where to write output probability CSVs")
    ap.add_argument("--batch-size", type=int, default=128, help="Inference batch size (default: 128)")
    ap.add_argument(
        "--device", default="auto", choices=("auto", "cuda", "mps", "cpu"), help="Device override (default: auto)"
    )
    ap.add_argument("--models", default="rca,resnet", help='Comma-separated models (default: "rca,resnet")')
    ap.add_argument(
        "--folders",
        default="SEDplot,SEDrplot,AllWISE,DTDM",
        help='Comma-separated folders (default: "SEDplot,SEDrplot,AllWISE,DTDM")',
    )
    args = ap.parse_args()

    runroot = Path(args.runroot)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    folders = [x.strip() for x in args.folders.split(",") if x.strip()]
    models = [x.strip() for x in args.models.split(",") if x.strip()]
    if not models:
        models = list(MODELS_DEFAULT)

    device = detect_device() if args.device == "auto" else args.device
    print(f"[customclass] device = {device}")

    here = Path(__file__).resolve().parent
    demo_infer = here / "yso_custom_models_final" / "demo_infer.py"
    if not demo_infer.exists():
        raise SystemExit(f"ERROR: Missing demo_infer.py at: {demo_infer}")

    any_fail = False

    for folder_name in folders:
        data_folder = runroot / folder_name
        if not data_folder.is_dir():
            print(f"[SKIP] Missing folder: {data_folder}")
            continue

        # If folder has zero png/jpg, skip (avoids confusing "success but empty")
        img_count = (
            len(list(data_folder.glob("*.png")))
            + len(list(data_folder.glob("*.jpg")))
            + len(list(data_folder.glob("*.jpeg")))
        )
        if img_count == 0:
            print(f"[SKIP] No images found in: {data_folder}")
            for model in models:
                (outdir / f"custom_{folder_name}_{model}.csv").write_text("name,p_yso,logit,y_hat\n")
            continue

        product_list = PRODUCT_CANDIDATES.get(folder_name, [folder_name.lower()])

        for model in models:
            out_csv = outdir / f"custom_{folder_name}_{model}.csv"

            ok = False
            last_rc = None

            for product in product_list:
                print(f"\n[RUN] folder={folder_name} model={model} product={product} images={img_count}")
                rc = run_demo_infer(
                    demo_infer=demo_infer,
                    data_folder=data_folder,
                    out_csv=out_csv,
                    product=product,
                    model=model,
                    device=device,
                    batch_size=args.batch_size,
                )
                last_rc = rc

                if rc == 0 and out_csv.exists():
                    ok = True
                    break

                print(f"[WARN] demo_infer failed for product='{product}' (rc={rc}). Trying next...")

            if not ok:
                print(f"[ERR] Failed: folder={folder_name} model={model}. Last rc={last_rc}.")
                any_fail = True

    raise SystemExit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
