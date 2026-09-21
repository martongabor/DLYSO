#!/usr/bin/env python3
"""Install the application, models and dust maps with one command."""

import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-dust", action="store_true", help="Skip CSFD maps")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    requirement = (
        f"{source}[gui]"
        if (source / "pyproject.toml").is_file()
        else "dlyso-pipeline[gui] @ git+https://github.com/martongabor/DLYSO.git"
    )
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", requirement], check=True)
    subprocess.run([sys.executable, "-m", "dlyso_setup", *(["--skip-dust"] if args.skip_dust else [])], check=True)


if __name__ == "__main__":
    main()
