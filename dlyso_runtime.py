"""Filesystem and process primitives shared by DLYSO entry points."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import sys
import subprocess
import tempfile
from pathlib import Path

VERSION = "1.1.0rc1"


def data_root() -> Path:
    """User-writable data location; independent of the Python installation."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "DLYSO"


def model_root() -> Path:
    if os.environ.get("DLYSO_MODEL_ROOT"):
        return Path(os.environ["DLYSO_MODEL_ROOT"]).expanduser().resolve()
    bundled = Path(__file__).resolve().parent / "scripts"
    if len(list(bundled.rglob("*.pt"))) == 48:
        return bundled
    return data_root() / "models" / VERSION / "scripts"


def require_models(modalities) -> None:
    from scripts.combineresult import PYTORCH_ARCHES

    products = {"SEDplot": "sed", "SEDrplot": "sedr", "AllWISE": "allwise", "DTDM": "dtdm"}
    for modality in modalities:
        paths = [model_root() / "models" / f"{modality}_{arch}_best.pt" for arch in PYTORCH_ARCHES]
        paths += [
            model_root() / "yso_custom_models_final/yso_bundle/assets" / f"{model}_{products[modality]}.pt"
            for model in ("rca", "resnet")
        ]
        missing = [str(p) for p in paths if not p.is_file()]
        if missing:
            raise FileNotFoundError(
                f"Missing {modality} models. Run dlyso-setup to install the models. First missing file: {missing[0]}"
            )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, suffix=".tmp", delete=False) as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def guard_input(runroot: Path, input_csv: Path, radius_arcsec=None) -> str:
    """Reject a different catalogue before any existing artifacts are changed."""
    fingerprint = sha256(input_csv)
    manifest = runroot / "run_manifest.json"
    if manifest.exists():
        previous = json.loads(manifest.read_text())
        old = previous.get("input_sha256")
        if old and old != fingerprint:
            raise ValueError("This project belongs to a different input catalogue. Choose a new project folder.")
        if not old:
            raise ValueError(
                "This legacy project has no input fingerprint. Keep it for reference and use a new folder."
            )
        old_radius = previous.get("parameters", {}).get("radius_arcsec")
        if radius_arcsec is not None and old_radius is not None and radius_arcsec != old_radius:
            raise ValueError("The SED query radius changed. Use a new project folder to avoid stale cached photometry.")
        root = Path(__file__).resolve().parent
        for name, expected in previous.get("software_sha256", {}).items():
            path = root / name
            if not path.is_file() or sha256(path) != expected:
                raise ValueError("Pipeline software changed since this project was created. Use a new project folder.")
        for name, expected in previous.get("models_sha256", {}).items():
            path = model_root() / name
            if not path.is_file() or sha256(path) != expected:
                raise ValueError("Model files changed since this project was created. Use a new project folder.")
    return fingerprint


def terminate_tree(process: subprocess.Popen, force: bool = False) -> None:
    """Stop a session and its descendants, including inference/data-loader workers."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            pass
    else:
        # taskkill /T includes descendants; only our launched PID is targeted.
        command = ["taskkill", "/PID", str(process.pid), "/T"]
        if force:
            command.append("/F")
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
