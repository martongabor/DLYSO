#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
scripts/combineresult.py

Create final result.csv using the input coordinate list as master.
For each source (ra,dec), attach all CNN architecture probabilities and the
custom ResNet/RCA probabilities for each selected modality.

Then compute, per modality, how many of the 12 classifiers
would classify the source as a YSO using fixed thresholds.

Columns use the compact ``<modality>_<model>`` naming convention.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd


MODALITIES = ["SEDplot", "SEDrplot", "AllWISE", "DTDM"]

PYTORCH_ARCHES = [
    "efficientnet_b0",
    "efficientnet_v2_s",
    "mnasnet0_5",
    "mobilenet_v3_small",
    "regnet_y_400mf",
    "resnet18",
    "resnet50",
    "resnext50_32x4d",
    "shufflenet_v2_x0_5",
    "squeezenet1_1",
]

THRESHOLDS: Dict[str, Dict[str, float]] = {
    "SEDplot": {
        "efficientnet_b0": 0.383,
        "efficientnet_v2_s": 0.508,
        "mnasnet0_5": 0.265,
        "mobilenet_v3_small": 0.598,
        "regnet_y_400mf": 0.655,
        "resnet18": 0.598,
        "resnet50": 0.484,
        "resnext50_32x4d": 0.457,
        "shufflenet_v2_x0_5": 0.402,
        "squeezenet1_1": 0.194,
        "custom_resnet": 0.47,
        "custom_rca": 0.65,
    },
    "SEDrplot": {
        "efficientnet_b0": 0.898,
        "efficientnet_v2_s": 0.493,
        "mnasnet0_5": 0.938,
        "mobilenet_v3_small": 0.857,
        "regnet_y_400mf": 0.558,
        "resnet18": 0.653,
        "resnet50": 0.801,
        "resnext50_32x4d": 0.617,
        "shufflenet_v2_x0_5": 0.757,
        "squeezenet1_1": 0.757,
        "custom_resnet": 0.65,
        "custom_rca": 0.71,
    },
    "AllWISE": {
        "efficientnet_b0": 0.454,
        "efficientnet_v2_s": 0.720,
        "mnasnet0_5": 0.553,
        "mobilenet_v3_small": 0.477,
        "regnet_y_400mf": 0.486,
        "resnet18": 0.503,
        "resnet50": 0.501,
        "resnext50_32x4d": 0.470,
        "shufflenet_v2_x0_5": 0.596,
        "squeezenet1_1": 0.365,
        "custom_resnet": 0.58,
        "custom_rca": 0.5,
    },
    "DTDM": {
        "efficientnet_b0": 0.585,
        "efficientnet_v2_s": 0.334,
        "mnasnet0_5": 0.490,
        "mobilenet_v3_small": 0.477,
        "regnet_y_400mf": 0.489,
        "resnet18": 0.545,
        "resnet50": 0.553,
        "resnext50_32x4d": 0.519,
        "shufflenet_v2_x0_5": 0.408,
        "squeezenet1_1": 0.482,
        "custom_resnet": 0.48,
        "custom_rca": 0.5,
    },
}


def _round_key(df: pd.DataFrame, ndp: int) -> pd.DataFrame:
    df = df.copy()
    df["_ra_key"] = df["ra"].astype(float).round(ndp)
    df["_dec_key"] = df["dec"].astype(float).round(ndp)
    return df


def _ensure_radec(df: pd.DataFrame) -> pd.DataFrame:
    if "ra" in df.columns and "dec" in df.columns:
        return df

    for c in ["name", "filename", "file", "image", "img", "path"]:
        if c in df.columns:
            s = df[c].astype(str)
            s = s.str.replace("\\\\", "/", regex=False).str.split("/").str[-1]
            s = (
                s.str.replace(".png", "", regex=False)
                .str.replace(".jpg", "", regex=False)
                .str.replace(".jpeg", "", regex=False)
            )
            parts = s.str.split("_", n=1, expand=True)
            if parts.shape[1] >= 2:
                df = df.copy()
                df["ra"] = pd.to_numeric(parts[0], errors="coerce")
                df["dec"] = pd.to_numeric(parts[1], errors="coerce")
            break
    return df


def load_classprobs(path: Path, modality: str, ndp: int) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["_ra_key", "_dec_key"])

    df = pd.read_csv(path)
    df = _ensure_radec(df)

    if "ra" not in df.columns or "dec" not in df.columns:
        return pd.DataFrame(columns=["_ra_key", "_dec_key"])

    df = df[df["ra"].notna() & df["dec"].notna()]
    df = _round_key(df, ndp)

    keep = ["_ra_key", "_dec_key"]
    ren = {}

    for arch in PYTORCH_ARCHES:
        col = f"p_yso_{arch}"
        if col in df.columns:
            keep.append(col)
            ren[col] = f"{modality}_{arch}"

    return df[keep].drop_duplicates(subset=["_ra_key", "_dec_key"]).rename(columns=ren)


def _pick_prob_column(df: pd.DataFrame) -> Optional[str]:
    ignore = {"ra", "dec", "_ra_key", "_dec_key", "filename", "name"}
    for c in df.columns:
        cl = c.lower()
        if c not in ignore and (cl.startswith("p_") or "prob" in cl or "yso" in cl):
            return c
    num_cols = [c for c in df.columns if c not in ignore and pd.api.types.is_numeric_dtype(df[c])]
    return num_cols[-1] if num_cols else None


def load_custom(path: Path, modality: str, custom_model: str, ndp: int) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["_ra_key", "_dec_key"])

    df = pd.read_csv(path)
    df = _ensure_radec(df)

    if "ra" not in df.columns or "dec" not in df.columns:
        return pd.DataFrame(columns=["_ra_key", "_dec_key"])

    df = df[df["ra"].notna() & df["dec"].notna()]
    df = _round_key(df, ndp)

    prob_col = _pick_prob_column(df)
    if prob_col is None:
        return pd.DataFrame(columns=["_ra_key", "_dec_key"])

    return (
        df[["_ra_key", "_dec_key", prob_col]]
        .drop_duplicates(subset=["_ra_key", "_dec_key"])
        .rename(columns={prob_col: f"{modality}_custom_{custom_model}"})
    )


def count_votes(row: pd.Series, modality: str):
    th = THRESHOLDS[modality]
    votes = 0

    for arch in PYTORCH_ARCHES:
        v = row.get(f"{modality}_{arch}", np.nan)
        if pd.notna(v) and v >= th[arch]:
            votes += 1

    for m in ("resnet", "rca"):
        v = row.get(f"{modality}_custom_{m}", np.nan)
        if pd.notna(v) and v >= th[f"custom_{m}"]:
            votes += 1

    columns = [f"{modality}_{model}" for model in th]
    return votes if any(pd.notna(row.get(c, np.nan)) for c in columns) else pd.NA


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_csv")
    ap.add_argument("--classprobs", default="myrun/ClassProbs")
    ap.add_argument("--customclass", default="myrun/customClass")
    ap.add_argument("--outcsv", default="myrun/result.csv")
    ap.add_argument("--ndp", type=int, default=6)
    ap.add_argument(
        "--modalities", default=",".join(MODALITIES), help="Comma-separated modalities to include in the result"
    )
    ap.add_argument("--available-modalities", default=None, help="Only read predictions for completed channels")
    args = ap.parse_args()

    master = pd.read_csv(args.input_csv)
    if "ra" not in master.columns or "dec" not in master.columns:
        raise SystemExit("Input CSV must contain ra, dec")

    master = master[master["ra"].notna() & master["dec"].notna()]
    master = _round_key(master, args.ndp)

    modalities = [value.strip() for value in args.modalities.split(",") if value.strip()]
    unknown = sorted(set(modalities) - set(MODALITIES))
    if unknown:
        raise SystemExit(f"Unknown modalities: {', '.join(unknown)}")

    for modality in modalities:
        if args.available_modalities is None or modality in args.available_modalities.split(","):
            cp = load_classprobs(Path(args.classprobs) / f"class_{modality}.csv", modality, args.ndp)
            master = master.merge(cp, on=["_ra_key", "_dec_key"], how="left")

            for custom_model in ("resnet", "rca"):
                m = load_custom(
                    Path(args.customclass) / f"custom_{modality}_{custom_model}.csv", modality, custom_model, args.ndp
                )
                master = master.merge(m, on=["_ra_key", "_dec_key"], how="left")

        probability_columns = [f"{modality}_{model}" for model in THRESHOLDS[modality]]
        for column in probability_columns:
            if column not in master:
                master[column] = np.nan
            master[column] = pd.to_numeric(master[column], errors="coerce")
            invalid = master[column].notna() & ~master[column].between(0, 1)
            if invalid.any():
                raise SystemExit(f"Invalid probability outside [0, 1] in {column}")
        master[f"{modality}_n_models"] = master[probability_columns].notna().sum(axis=1)
        master[f"{modality}_status"] = master[f"{modality}_n_models"].map(
            lambda count: "not_evaluated" if count == 0 else ("complete" if count == 12 else "partial")
        )

        master[f"{modality}_votes"] = master.apply(lambda r: count_votes(r, modality), axis=1).astype("Int64")

    master.drop(columns=["_ra_key", "_dec_key"], inplace=True, errors="ignore")
    Path(args.outcsv).parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(args.outcsv).with_suffix(".csv.part")
    master.to_csv(temporary, index=False)
    temporary.replace(args.outcsv)

    print(f"[OK] Final result written to {Path(args.outcsv).resolve()}")
    print(f"Rows: {len(master)}")


if __name__ == "__main__":
    main()
