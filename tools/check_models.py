#!/usr/bin/env python3
"""CPU smoke check: strict weight loading and finite outputs for all 48 models."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/yso_custom_models_final"))

import torch
from dlyso_runtime import model_root
from yso_bundle.infer import load_model


def main():
    spec = importlib.util.spec_from_file_location("ensemble", ROOT / "scripts/class.py")
    ensemble = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ensemble)
    torch.set_num_threads(2)
    rows = []
    with torch.inference_mode():
        for path in sorted((model_root() / "models").glob("*.pt")):
            net, arch, classes, size, yso_index = ensemble.load_checkpoint_as_model(path, torch.device("cpu"))
            result = net(torch.zeros(1, 3, size, size))
            assert result.shape == (1, len(classes)) and torch.isfinite(result).all(), path
            rows.append(
                {
                    "file": path.name,
                    "shape": list(result.shape),
                    "image_size": size,
                    "classes": classes,
                    "yso_index": yso_index,
                }
            )
            print(f"OK {path.name}", flush=True)
            del net
        for product in ["sed", "sedr", "allwise", "dtdm"]:
            for model in ["resnet", "rca"]:
                net, cfg = load_model(product, model, "cpu")
                width, height = cfg["preprocess"]["target_size"]
                channels = 1 if cfg["preprocess"]["as_gray"] else 3
                result = net(torch.zeros(1, channels, height, width))
                assert result.numel() == 1 and torch.isfinite(result).all()
                rows.append({"file": cfg["asset_state_dict"], "shape": list(result.shape)})
                print(f"OK {cfg['asset_state_dict']}", flush=True)
                del net
    assert len(rows) == 48, f"Expected 48 models, checked {len(rows)}"
    output = ROOT / "docs/model-smoke.json"
    output.write_text(
        json.dumps({"device": "cpu", "input": "synthetic zeros; not an accuracy test", "models": rows}, indent=2) + "\n"
    )
    print(f"48 / 48 passed. Report: {output}")


if __name__ == "__main__":
    main()
