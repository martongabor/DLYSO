# demo_infer.py
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import torch

from yso_bundle import available_models, load_model, predict_split_batched, predict_folder_batched


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--product", required=True, choices=["sed", "sedr", "allwise", "dtdm"])
    ap.add_argument("--model", required=True, choices=["resnet", "rca"])

    ap.add_argument(
        "--data_root",
        default=None,
        help="Path to base training folder (contains SEDplot/SEDrplot/AllWISE/DTDM) OR directly to the product folder. "
        "Required if --split is {train,valid,test}.",
    )
    ap.add_argument(
        "--split",
        required=True,
        help="One of {train, valid, test} OR a folder path containing *.png files (non-recursive).",
    )

    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--out_csv", default="yso_predictions.csv")
    ap.add_argument("--thr", type=float, default=0.15, help="Decision threshold on p_yso for y_hat")
    ap.add_argument("--batch_size", type=int, default=128, help="Batch size for inference")
    args = ap.parse_args()

    # show what's available
    _ = available_models()

    split_lower = str(args.split).lower()
    is_known_split = split_lower in {"train", "valid", "test"}

    if is_known_split and not args.data_root:
        raise ValueError("--data_root is required when --split is train/valid/test")

    # Force-load once so we can print cfg used
    _, cfg = load_model(product=args.product, model=args.model, device=args.device)

    if is_known_split:
        rows = predict_split_batched(
            product=args.product,
            model=args.model,
            data_root=str(args.data_root),
            split=split_lower,
            device=args.device,
            batch_size=args.batch_size,
        )
        for r in rows:
            r["y_hat"] = int(r["p_yso"] >= args.thr)

        # write csv
        fieldnames = ["path", "y_true", "p_yso", "logit", "y_hat"]
        with open(args.out_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k) for k in fieldnames})

        # F1@thr
        ys = np.array([r["y_true"] for r in rows], dtype=int)
        yh = np.array([r["y_hat"] for r in rows], dtype=int)

        tp = int(((yh == 1) & (ys == 1)).sum())
        fp = int(((yh == 1) & (ys == 0)).sum())
        fn = int(((yh == 0) & (ys == 1)).sum())

        denom = 2 * tp + fp + fn
        f1 = float((2 * tp) / denom) if denom > 0 else 0.0

        print("Config used:", cfg)
        print(f"Done. N={len(rows)} F1@thr={f1:.4f}  out={args.out_csv}")
        return

    # Otherwise: treat --split as folder path
    folder = Path(args.split)
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"--split was not a known split and is not a folder: {folder}")

    rows = predict_folder_batched(
        product=args.product,
        model=args.model,
        folder=str(folder),
        device=args.device,
        batch_size=args.batch_size,
    )
    for r in rows:
        r["y_hat"] = int(r["p_yso"] >= args.thr)
        r["name"] = Path(r["path"]).name

    # write csv (no y_true)
    fieldnames = ["name", "p_yso", "logit", "y_hat"]
    with open(args.out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fieldnames})

    print("Config used:", cfg)
    print(f"Done. N={len(rows)}  out={args.out_csv}")


if __name__ == "__main__":
    main()
