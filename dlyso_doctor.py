"""Check a DLYSO installation without downloading data or loading checkpoints."""

from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
from dlyso_runtime import VERSION, model_root, sha256
from scripts.combineresult import MODALITIES, PYTORCH_ARCHES


def inspect_installation(verify=False):
    issues = []
    for name in [
        "numpy",
        "pandas",
        "PIL",
        "matplotlib",
        "astropy",
        "astroquery",
        "dustmaps",
        "torch",
        "torchvision",
        "requests",
    ]:
        if importlib.util.find_spec(name) is None:
            issues.append(f"Missing Python module: {name}")
    expected = [f"models/{modality}_{arch}_best.pt" for modality in MODALITIES for arch in PYTORCH_ARCHES]
    expected += [
        f"yso_custom_models_final/yso_bundle/assets/{model}_{product}.pt"
        for model in ["resnet", "rca"]
        for product in ["sed", "sedr", "allwise", "dtdm"]
    ]
    for name in expected:
        if not (model_root() / name).is_file():
            issues.append(f"Missing checkpoint: {name}")
    manifest_path = Path(__file__).resolve().parent / "dlyso_assets/model-manifest.json"
    if verify:
        if not manifest_path.exists():
            issues.append("No model checksum manifest is installed.")
        else:
            for name, digest in json.loads(manifest_path.read_text())["sha256"].items():
                path = model_root() / name
                if path.is_file() and sha256(path) != digest:
                    issues.append(f"Checksum mismatch: {name}")
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-models", action="store_true", help="Read all checkpoint bytes and compare SHA-256 hashes"
    )
    args = parser.parse_args()
    print(f"DLYSO {VERSION}\nModel root: {model_root()}")
    print("Desktop toolkit: " + ("available" if importlib.util.find_spec("PySide6") else "not installed (optional)"))
    issues = inspect_installation(args.verify_models)
    for issue in issues:
        print(f"FAIL  {issue}")
    if issues:
        raise SystemExit(1)
    print("OK  Runtime modules and all 48 model files are present.")
    if args.verify_models:
        print("OK  Model checksums match the release manifest.")
    print("Network access, GPU compatibility and CSFD map data are checked when their stages run.")


if __name__ == "__main__":
    main()
