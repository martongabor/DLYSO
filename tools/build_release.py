#!/usr/bin/env python3
"""Assemble local review archives from an explicit allowlist; never upload."""

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dlyso_runtime import VERSION, model_root, sha256


def archive(destination, files, prefix):
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path, relative in sorted(files, key=lambda item: item[1]):
            info = zipfile.ZipInfo(f"{prefix}/{relative}", date_time=(2026, 9, 14, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if path.suffix == ".pt" else zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with path.open("rb") as source, output.open(info, "w", force_zip64=True) as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)


def main():
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    top = [
        "README.md",
        "CHANGELOG.md",
        "CITATION.bib",
        "pyproject.toml",
        "MANIFEST.in",
        "install.py",
        "requirements.txt",
        "requirements-dev.txt",
        "constraints-tested.txt",
        ".gitignore",
        "dlyso_pipeline_docs.html",
    ]
    top += [path.name for path in ROOT.glob("dlyso*.py")]
    top += [name for name in ["LICENSE", "CITATION.cff"] if (ROOT / name).is_file()]
    paths = [ROOT / name for name in top]
    extensions = {".py", ".md", ".json", ".html", ".csv", ".png", ".yml"}
    for folder in ["docs", "tests", "tools", "examples", "dlyso_assets", ".github"]:
        paths += [
            path
            for path in (ROOT / folder).rglob("*")
            if path.is_file() and path.suffix in extensions and "__pycache__" not in path.parts
        ]
    paths += [path for path in (ROOT / "scripts").rglob("*") if path.is_file() and path.suffix in {".py", ".json"}]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing release inputs: {missing}")
    source = dist / f"dlyso-{VERSION}.zip"
    archive(source, [(path, str(path.relative_to(ROOT))) for path in set(paths)], f"dlyso-{VERSION}")
    weights = sorted(model_root().rglob("*.pt"))
    if len(weights) != 48:
        raise SystemExit(f"Expected 48 model files, found {len(weights)}")
    models = dist / f"dlyso-models-{VERSION}.zip"
    archive(models, [(path, str(path.relative_to(model_root()))) for path in weights], "scripts")
    checksums = {path.name: sha256(path) for path in [source, models, *dist.glob("*.whl")]}
    (dist / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in sorted(checksums.items())))
    (dist / "release-inventory.json").write_text(
        json.dumps(
            {
                "version": VERSION,
                "source_files": len(set(paths)),
                "model_files": len(weights),
                "sha256": checksums,
                "publication_metadata_complete": all((ROOT / name).exists() for name in ["LICENSE", "CITATION.cff"]),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Built {source.name} and {models.name}. Checksums: {dist / 'SHA256SUMS'}")
    if not all((ROOT / name).exists() for name in ["LICENSE", "CITATION.cff"]):
        print("Review archives only: finalize authorship, license and model redistribution rights before publishing.")


if __name__ == "__main__":
    main()
