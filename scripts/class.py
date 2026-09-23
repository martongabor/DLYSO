#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Ensemble inference using the supplied checkpoint metadata.

- Reads checkpoints: scripts/models/<TYPE>_<ARCH>_best.pt
- Resizes images to the checkpoint's img_size (ref from first ckpt)
- Uses Softmax over logits (not sigmoid)
- Determines YSO index from ckpt["classes"] (no assumption class-1)
- Optional AMP on cuda/mps and channels_last like orig

Outputs:
  <outdir>/class_<TYPE>.csv
Columns:
  filename, ra, dec, avg_p_yso, p_yso_<arch>...
"""

from __future__ import annotations

import argparse
import sys
import re
from pathlib import Path
from typing import List, Dict, Optional

import pandas as pd
from PIL import Image

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import torchvision
from torchvision import transforms


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dlyso_runtime import model_root


IMG_EXTS = {".png", ".jpg", ".jpeg"}
_RA_DEC_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)_([+-]?\d+(?:\.\d+)?)", re.ASCII)


def best_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def parse_ra_dec_from_name(name: str):
    stem = Path(name).stem
    try:
        ra, dec = stem.split("_", 1)
        return float(ra), float(dec)
    except ValueError:
        return None, None


class ImgFolderDataset(Dataset):
    """Loads images from a folder; converts to RGB; applies resize+ToTensor (no normalization)."""

    def __init__(self, image_dir: Path, img_size: int):
        self.dir = image_dir
        self.files = sorted([p for p in self.dir.iterdir() if p.suffix.lower() in IMG_EXTS])
        self.tf = transforms.Compose(
            [
                transforms.Resize((img_size, img_size)),
                transforms.ToTensor(),  # IMPORTANT: no normalization (matches orig)
            ]
        )

    def __len__(self):
        return len(self.files)

    def __getitem__(self, idx):
        p = self.files[idx]
        img = Image.open(p).convert("RGB")
        x = self.tf(img)
        return x, p.name


def choose_yso_index(class_list) -> int:
    """
    Match orig behavior:
    - Prefer explicit "YSO" (case-insensitive)
    - If binary and contains 'other', choose the non-'other'
    - Otherwise default to 0
    """
    try:
        for i, c in enumerate(class_list):
            if isinstance(c, str) and c.lower() == "yso":
                return i
        if len(class_list) == 2 and any((isinstance(c, str) and c.lower() == "other") for c in class_list):
            return 0 if str(class_list[0]).lower() != "other" else 1
    except Exception:
        pass
    return 0


def _replace_last_linear(seq: nn.Sequential, out_features: int):
    last_lin_idx = None
    for idx, m in reversed(list(enumerate(seq))):
        if isinstance(m, nn.Linear):
            last_lin_idx = idx
            in_features = m.in_features
            break
    if last_lin_idx is None:
        raise ValueError("No nn.Linear found in Sequential classifier.")
    seq[last_lin_idx] = nn.Linear(in_features, out_features)


def build_model_by_arch(arch: str, num_classes: int) -> nn.Module:
    """
    Support the exact arches you listed (no inception).
    Rebuild a torchvision architecture and replace its classification head.
    """
    a = arch.lower()

    if a == "resnet18":
        m = torchvision.models.resnet18(weights=None)
        m.fc = nn.Linear(m.fc.in_features, num_classes)

    elif a == "resnet50":
        m = torchvision.models.resnet50(weights=None)
        m.fc = nn.Linear(m.fc.in_features, num_classes)

    elif a == "resnext50_32x4d":
        m = torchvision.models.resnext50_32x4d(weights=None)
        m.fc = nn.Linear(m.fc.in_features, num_classes)

    elif a == "efficientnet_b0":
        m = torchvision.models.efficientnet_b0(weights=None)
        if isinstance(m.classifier, nn.Sequential):
            _replace_last_linear(m.classifier, num_classes)
        else:
            raise ValueError(f"Unexpected classifier for {arch}: {type(m.classifier)}")

    elif a == "efficientnet_v2_s":
        m = torchvision.models.efficientnet_v2_s(weights=None)
        if isinstance(m.classifier, nn.Sequential):
            _replace_last_linear(m.classifier, num_classes)
        else:
            raise ValueError(f"Unexpected classifier for {arch}: {type(m.classifier)}")

    elif a == "mnasnet0_5":
        m = torchvision.models.mnasnet0_5(weights=None)
        # classifier: Sequential(Dropout, Linear)
        if (
            isinstance(m.classifier, nn.Sequential)
            and len(m.classifier) >= 2
            and isinstance(m.classifier[1], nn.Linear)
        ):
            m.classifier[1] = nn.Linear(m.classifier[1].in_features, num_classes)
        else:
            raise ValueError(f"Unexpected classifier for {arch}: {m.classifier}")

    elif a == "mobilenet_v3_small":
        m = torchvision.models.mobilenet_v3_small(weights=None)
        # classifier: Sequential(..., Linear at the end)
        if isinstance(m.classifier, nn.Sequential):
            _replace_last_linear(m.classifier, num_classes)
        else:
            raise ValueError(f"Unexpected classifier for {arch}: {type(m.classifier)}")

    elif a == "regnet_y_400mf":
        m = torchvision.models.regnet_y_400mf(weights=None)
        m.fc = nn.Linear(m.fc.in_features, num_classes)

    elif a == "shufflenet_v2_x0_5":
        m = torchvision.models.shufflenet_v2_x0_5(weights=None)
        m.fc = nn.Linear(m.fc.in_features, num_classes)

    elif a == "squeezenet1_1":
        m = torchvision.models.squeezenet1_1(weights=None)
        # classifier: Sequential(Dropout, Conv2d(512,1000,1), ReLU, AvgPool)
        if isinstance(m.classifier, nn.Sequential) and isinstance(m.classifier[1], nn.Conv2d):
            conv = m.classifier[1]
            m.classifier[1] = nn.Conv2d(conv.in_channels, num_classes, kernel_size=conv.kernel_size, stride=conv.stride)
        else:
            raise ValueError(f"Unexpected classifier for {arch}: {type(m.classifier)}")

    else:
        raise ValueError(f"Unsupported arch: {arch}")

    return m


def load_checkpoint_as_model(path: Path, device: torch.device, channels_last: bool = True):
    """
    Checkpoint formats:
    - ckpt is dict with keys like: state_dict, classes, img_size, arch
    - if file is raw state_dict, we fallback with defaults inferred from filename
    """
    ckpt = torch.load(path, map_location=device)

    if isinstance(ckpt, dict) and "state_dict" in ckpt:
        state_dict = ckpt["state_dict"]
        arch = ckpt.get("arch", None)
        classes = ckpt.get("classes", ["YSO", "other"])
        img_size = int(ckpt.get("img_size", 224))
    else:
        state_dict = ckpt
        arch = None
        classes = ["YSO", "other"]
        img_size = 224

    # Infer arch from filename if missing
    if not arch:
        # <TYPE>_<ARCH>_best.pt  -> arch
        arch = path.name.split("_", 1)[1].replace("_best.pt", "")

    num_classes = len(classes) if isinstance(classes, (list, tuple)) and len(classes) >= 2 else 2
    model = build_model_by_arch(str(arch), num_classes)
    model.load_state_dict(state_dict, strict=True)
    model.to(device)
    if channels_last:
        model.to(memory_format=torch.channels_last)
    model.eval()

    yso_idx = choose_yso_index(classes)
    return model, str(arch), classes, img_size, int(yso_idx)


@torch.no_grad()
def infer_type(
    dtype: str,
    runroot: Path,
    models_dir: Path,
    outdir: Path,
    device: torch.device,
    batch_size: int,
    num_workers: int,
    channels_last: bool = True,
):
    img_dir = runroot / dtype
    out_csv = outdir / f"class_{dtype}.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    if not img_dir.is_dir():
        raise FileNotFoundError(f"Missing input folder: {img_dir}")

    ckpts = sorted(models_dir.glob(f"{dtype}_*_best.pt"))
    if not ckpts:
        raise FileNotFoundError(f"No checkpoints found: {models_dir}/{dtype}_*_best.pt")

    if not any(p.suffix.lower() in IMG_EXTS for p in img_dir.iterdir()):
        pd.DataFrame(columns=["filename", "ra", "dec"]).to_csv(out_csv, index=False)
        print(f"[EMPTY] {dtype}: no usable images; sources will be marked not_evaluated.")
        return

    # Load models, and pick a reference img_size from the FIRST checkpoint (orig behavior)
    models: List[Dict[str, object]] = []
    ref_img_size: Optional[int] = None

    for ck in ckpts:
        m, arch, classes, img_size, yso_idx = load_checkpoint_as_model(ck, device, channels_last=channels_last)
        models.append({"model": m, "arch": arch, "yso_idx": yso_idx})
        if ref_img_size is None:
            ref_img_size = img_size
        elif img_size != ref_img_size:
            raise ValueError(f"Mixed image sizes in {dtype} checkpoints; refusing inconsistent preprocessing.")

    assert ref_img_size is not None
    ds = ImgFolderDataset(img_dir, img_size=ref_img_size)

    if len(ds) == 0:
        pd.DataFrame([{"error": f"No images in {img_dir}"}]).to_csv(out_csv, index=False)
        return

    dl = DataLoader(
        ds,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=(device.type == "cuda"),
    )

    sm = nn.Softmax(dim=1)
    use_amp = device.type in {"cuda", "mps"}
    amp_dtype = torch.bfloat16 if (device.type == "cuda" and torch.cuda.is_bf16_supported()) else torch.float16

    rows = []
    for batch, names in dl:
        batch = batch.to(device, non_blocking=True)
        if channels_last:
            batch = batch.to(memory_format=torch.channels_last)

        per_model_probs = []
        arch_names = []
        for entry in models:
            m = entry["model"]
            yidx = int(entry["yso_idx"])
            with torch.autocast(device_type=device.type, dtype=amp_dtype, enabled=use_amp):
                logits = m(batch)
            # AMP outputs can be bfloat16, which cannot be exported directly to NumPy.
            # Compute probabilities and ensemble averages in float32 on every device.
            probs = sm(logits.float())
            yidx = max(0, min(yidx, probs.shape[1] - 1))
            per_model_probs.append(probs[:, yidx])
            arch_names.append(str(entry["arch"]))

        probs_stack = torch.stack(per_model_probs, dim=1)  # [B, M]
        avg_p_yso = probs_stack.mean(dim=1).clamp(0, 1)

        avg_np = avg_p_yso.cpu().numpy()
        per_np = [p.cpu().numpy() for p in per_model_probs]

        for i, name in enumerate(names):
            ra, dec = parse_ra_dec_from_name(name)
            row = {
                "filename": name,
                "ra": ra,
                "dec": dec,
                "avg_p_yso": float(avg_np[i]),
            }
            for j, arch in enumerate(arch_names):
                row[f"p_yso_{arch}"] = float(per_np[j][i])
            rows.append(row)

    pd.DataFrame(rows).to_csv(out_csv, index=False)


def main():
    ap = argparse.ArgumentParser(description="Run the supplied PyTorch ensemble for selected modalities.")
    ap.add_argument("--runroot", default="myrun", help="Root containing SEDplot/SEDrplot/DTDM/AllWISE folders")
    ap.add_argument("--models-dir", default=None, help="Folder with TYPE_<arch>_best.pt")
    ap.add_argument("--outdir", default="myrun/ClassProbs", help="Output folder for class_<TYPE>.csv")
    ap.add_argument("--types", default="SEDplot,SEDrplot,DTDM,AllWISE", help="Comma-separated types to run")
    ap.add_argument("--device", default="auto", choices=("auto", "cuda", "mps", "cpu"), help="Device override")
    ap.add_argument("--batch-size", type=int, default=128, help="Batch size")
    ap.add_argument("--num-workers", type=int, default=4, help="DataLoader workers")
    ap.add_argument("--channels-last", action="store_true", help="Use channels_last (matches orig)")
    args = ap.parse_args()

    models_dir = Path(args.models_dir) if args.models_dir else (model_root() / "models")
    runroot = Path(args.runroot)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    device = best_device() if args.device == "auto" else torch.device(args.device)

    types = [t.strip() for t in args.types.split(",") if t.strip()]
    for dtype in types:
        infer_type(
            dtype=dtype,
            runroot=runroot,
            models_dir=models_dir,
            outdir=outdir,
            device=device,
            batch_size=args.batch_size,
            num_workers=args.num_workers,
            channels_last=args.channels_last,
        )


if __name__ == "__main__":
    main()
