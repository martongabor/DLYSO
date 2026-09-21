from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

import torch
from torch.utils.data import DataLoader

from .dataset import SplitImageDataset, FlatFolderDataset
from .model import SmallResNet, ResConvAttnClassifier


def _load_manifest(bundle_dir: Path) -> Dict[str, Any]:
    p = bundle_dir / "assets" / "manifest.json"
    return json.loads(p.read_text())


def available_models() -> Dict[str, Any]:
    """
    Returns manifest["models"] mapping.
    """
    bundle_dir = Path(__file__).resolve().parent
    m = _load_manifest(bundle_dir)
    return m["models"]


def _norm_product(p: str) -> str:
    p = str(p).strip().lower()
    aliases = {
        "sedplot": "sed",
        "sed": "sed",
        "sedrplot": "sedr",
        "sedr": "sedr",
        "allwise": "allwise",
        "dtdm": "dtdm",
    }
    if p not in aliases:
        raise ValueError(f"Unknown product={p!r}. Use one of: {sorted(set(aliases.values()))}")
    return aliases[p]


def _norm_model(m: str) -> str:
    m = str(m).strip().lower()
    aliases = {
        "resnet": "resnet",
        "small_resnet": "resnet",
        "rca": "rca",
        "palette": "rca",
        "palette_encoder": "rca",
    }
    if m not in aliases:
        raise ValueError(f"Unknown model={m!r}. Use 'resnet' or 'rca'.")
    return aliases[m]


def load_model(
    product: str,
    model: str,
    device: str | torch.device = "cpu",
) -> Tuple[torch.nn.Module, Dict[str, Any]]:
    """
    Loads (model, cfg) from assets based on product/model.
    """
    product = _norm_product(product)
    model = _norm_model(model)

    device = torch.device(device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("device='cuda' requested but CUDA is not available.")

    # Speed hint when image size is fixed
    if device.type == "cuda":
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False

    bundle_dir = Path(__file__).resolve().parent
    manifest = _load_manifest(bundle_dir)
    try:
        entry = manifest["models"][product][model]
    except KeyError:
        raise KeyError(f"No exported model for product={product!r}, model={model!r}")

    cfg_path = bundle_dir / "assets" / entry["config"]
    cfg = json.loads(cfg_path.read_text())

    external = os.environ.get("DLYSO_MODEL_ROOT")
    asset_dir = (
        (Path(external).expanduser() / "yso_custom_models_final/yso_bundle/assets")
        if external
        else bundle_dir / "assets"
    )
    sd_path = asset_dir / cfg["asset_state_dict"]
    state_dict = torch.load(sd_path, map_location="cpu")

    arch = cfg["arch"]
    kw = dict(cfg["model_kwargs"])

    if arch == "SmallResNet":
        net = SmallResNet(**kw).to(device)
    elif arch == "ResConvAttnClassifier":
        net = ResConvAttnClassifier(**kw).to(device)
    else:
        raise ValueError(f"Unknown cfg['arch']={arch!r}")

    net.load_state_dict(state_dict, strict=True)
    net.eval()
    return net, cfg


def _make_loader(ds, batch_size: int, device: torch.device) -> DataLoader:
    # conservative default; still faster than pure Python loops
    ncpu = os.cpu_count() or 0
    num_workers = 4 if ncpu >= 8 else (2 if ncpu >= 4 else 0)
    pin = device.type == "cuda"

    return DataLoader(
        ds,
        batch_size=int(batch_size),
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin,
        persistent_workers=(num_workers > 0),
        drop_last=False,
    )


@torch.no_grad()
def _predict_loader(net, loader: DataLoader, device: torch.device) -> Tuple[List[Dict[str, Any]], Optional[List[int]]]:
    rows: List[Dict[str, Any]] = []
    y_true: Optional[List[int]] = []  # if labels exist

    for batch in loader:
        x = batch["image"].to(device, non_blocking=True)  # [B,C,H,W]
        logits = net(x)

        if logits.ndim == 2 and logits.shape[1] == 1:
            logits = logits[:, 0]
        if logits.ndim != 1:
            raise ValueError(f"Unexpected logits shape: {tuple(logits.shape)}")

        probs = torch.sigmoid(logits)

        # move to CPU once
        probs_cpu = probs.detach().cpu().tolist()
        logits_cpu = logits.detach().cpu().tolist()
        paths = batch["path"]

        has_label = "label" in batch
        if has_label:
            ys = batch["label"].detach().cpu().tolist()
            assert y_true is not None
            y_true.extend(int(v) for v in ys)

        for i in range(len(paths)):
            rows.append(
                {
                    "path": str(paths[i]),
                    "p_yso": float(probs_cpu[i]),
                    "logit": float(logits_cpu[i]),
                }
            )

    if y_true is None or len(y_true) == 0:
        return rows, None
    return rows, y_true


def _resolve_split_root(data_root: str, product_dir: str) -> Path:
    """
    Accept either:
      - data_root points to base folder containing product dirs
      - data_root points directly to the product dir
    """
    base = Path(data_root)

    # If user already passed .../<product_dir>
    if base.name == product_dir and base.exists():
        return base

    cand = base / product_dir
    if cand.exists():
        return cand

    raise FileNotFoundError(f"Could not resolve product folder. Tried: {base} and {cand}")


@torch.no_grad()
def predict_split_batched(
    product: str,
    model: str,
    data_root: str,
    split: str,
    device: str | torch.device = "cpu",
    batch_size: int = 128,
) -> List[Dict[str, Any]]:
    net, cfg = load_model(product=product, model=model, device=device)
    device = torch.device(device)

    root = _resolve_split_root(data_root, cfg["product_dir"])
    ds = SplitImageDataset(
        root_dir=str(root),
        split=str(split).lower(),
        class_to_idx=cfg["class_to_idx"],
        preprocess_cfg=cfg["preprocess"],
    )
    loader = _make_loader(ds, batch_size=batch_size, device=device)

    rows, y_true = _predict_loader(net, loader, device)
    assert y_true is not None

    for i, r in enumerate(rows):
        r["y_true"] = int(y_true[i])
    return rows


@torch.no_grad()
def predict_folder_batched(
    product: str,
    model: str,
    folder: str,
    device: str | torch.device = "cpu",
    batch_size: int = 128,
) -> List[Dict[str, Any]]:
    net, cfg = load_model(product=product, model=model, device=device)
    device = torch.device(device)

    ds = FlatFolderDataset(folder=str(folder), preprocess_cfg=cfg["preprocess"])
    loader = _make_loader(ds, batch_size=batch_size, device=device)

    rows, _ = _predict_loader(net, loader, device)
    return rows
