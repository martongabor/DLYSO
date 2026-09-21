"""Download, verify and install DLYSO models and CSFD data."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

import requests

from dlyso_runtime import VERSION, data_root, model_root, sha256

REPOSITORY = "martongabor/DLYSO"


def model_manifest():
    path = Path(__file__).resolve().parent / "dlyso_assets/model-manifest.json"
    document = json.loads(path.read_text())
    if document["version"] != VERSION:
        raise ValueError("Model manifest version does not match the application")
    return document["sha256"]


def verified(root, hashes):
    return all((root / name).is_file() and sha256(root / name) == digest for name, digest in hashes.items())


def fetch_archive(destination):
    name = f"dlyso-models-{VERSION}.zip"
    tag = f"v{VERSION}"
    url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"
    with requests.Session() as session:
        session.trust_env = False
        with session.get(url, stream=True, timeout=(15, 120)) as response:
            if response.status_code in {401, 403, 404}:
                gh = shutil.which("gh")
                if not gh and Path("/opt/homebrew/bin/gh").is_file():
                    gh = "/opt/homebrew/bin/gh"
                if not gh:
                    raise RuntimeError(
                        "Model release unavailable. For a private repository, install GitHub CLI and run gh auth login."
                    )
                subprocess.run(
                    [
                        gh,
                        "release",
                        "download",
                        tag,
                        "--repo",
                        REPOSITORY,
                        "--pattern",
                        name,
                        "--output",
                        str(destination),
                    ],
                    check=True,
                )
                return
            response.raise_for_status()
            total = int(response.headers.get("Content-Length", 0))
            received = 0
            next_report = 0
            with destination.open("wb") as output:
                for block in response.iter_content(1024 * 1024):
                    output.write(block)
                    received += len(block)
                    if received >= next_report:
                        print(
                            f"Model download: {received // (1024**2)} MiB"
                            + (f" / {total // (1024**2)} MiB" if total else ""),
                            flush=True,
                        )
                        next_report = received + 64 * 1024**2


def install_archive(archive, destination, hashes):
    """Validate a staged extraction before replacing any checkpoint."""
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dlyso-models-", dir=destination.parent) as temp:
        staged = Path(temp)
        with zipfile.ZipFile(archive) as bundle:
            expected = {f"scripts/{name}" for name in hashes}
            names = bundle.namelist()
            if len(names) != len(set(names)) or set(names) != expected:
                raise ValueError("Unexpected or missing files in the model archive")
            for name, digest in hashes.items():
                relative = Path(name)
                if relative.is_absolute() or ".." in relative.parts or "\\" in name:
                    raise ValueError("Unsafe model path")
                target = staged / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(f"scripts/{name}") as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                if sha256(target) != digest:
                    raise ValueError(f"Model checksum mismatch: {name}")
        for name in hashes:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            (staged / name).replace(target)


def setup_models():
    hashes = model_manifest()
    root = model_root()
    if verified(root, hashes):
        print(f"Models verified: {root}", flush=True)
        return root
    destination = (
        Path(os.environ["DLYSO_MODEL_ROOT"]).expanduser().resolve()
        if os.environ.get("DLYSO_MODEL_ROOT")
        else data_root() / "models" / VERSION / "scripts"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    print("Downloading 48 models (about 1.4 GiB).", flush=True)
    with tempfile.TemporaryDirectory(prefix=".download-", dir=destination.parent) as temp:
        archive = Path(temp) / "models.zip"
        fetch_archive(archive)
        install_archive(archive, destination, hashes)
    print(f"Models installed and verified: {destination}", flush=True)
    return destination


def setup_dust():
    from dustmaps.config import config
    from dustmaps.csfd import CSFDQuery, fetch

    try:
        CSFDQuery()
        print("CSFD maps are available.", flush=True)
        return
    except (OSError, ValueError):
        pass
    if not config.get("data_dir"):
        config["data_dir"] = str(data_root() / "dustmaps")
    print("Downloading CSFD maps from the official dustmaps data provider.", flush=True)
    fetch()
    CSFDQuery()
    print("CSFD maps installed.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-dust", action="store_true", help="Install models only, without CSFD maps")
    args = parser.parse_args()
    try:
        setup_models()
        if not args.skip_dust:
            setup_dust()
    except (OSError, ValueError, RuntimeError, requests.RequestException, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Setup failed: {exc}. Run dlyso-setup again to retry.") from exc
    print("Setup complete. Start the application with dlyso-gui.")


if __name__ == "__main__":
    main()
