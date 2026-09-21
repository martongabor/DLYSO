# GitHub installation

## Install the application

Install Python 3.10 or newer and Git. For this private repository, first sign in with GitHub CLI (`gh auth login`) and configure Git access (`gh auth setup-git`).

On Ubuntu/Debian, install the Qt system libraries before starting the GUI:

```bash
sudo apt-get update
sudo apt-get install -y libegl1 libopengl0
```

Create and activate a virtual environment, then install the application and data:

```bash
python -m pip install "dlyso-pipeline[gui] @ git+https://github.com/martongabor/DLYSO.git"
dlyso-setup
dlyso-gui
```

`dlyso-setup` downloads all 48 models from the matching GitHub Release, verifies their SHA-256 checksums and installs them automatically. It also checks for CSFD dust maps and downloads them from the official dustmaps data provider if missing. No manual ZIP download, extraction or model-path configuration is required.

The model download is about 1.4 GiB. Allow about 3 GiB of temporary space for downloading and unpacking it, plus space for CSFD maps and Python dependencies. Repeating setup verifies and reuses installed files. A failed download can be retried by running `dlyso-setup` again; partially downloaded archives are discarded.

Standard pip installation installs Python code and dependencies. The separate setup command installs the large data files. To perform both steps with one installer command from a clone:

```bash
git clone https://github.com/martongabor/DLYSO.git
cd DLYSO
python -m venv .venv
source .venv/bin/activate
python install.py
dlyso-gui
```

On Windows, activate with `.venv\Scripts\activate` instead. Run `python install.py --skip-dust` or `dlyso-setup --skip-dust` if you do not need the dust-aware SED channel.

For a fixed code version, append an existing tag or full commit hash after `.git`. See [pip's Git installation reference](https://pip.pypa.io/en/stable/topics/vcs-support/).

## Installed files

The default model directory is:

- macOS: `~/Library/Application Support/DLYSO/models/1.1.0rc1/scripts`
- Linux: `~/.local/share/DLYSO/models/1.1.0rc1/scripts` (or under `XDG_DATA_HOME`)
- Windows: `%LOCALAPPDATA%\DLYSO\models\1.1.0rc1\scripts`

The application finds this directory automatically. A complete set of models already present in a source checkout is reused. `DLYSO_MODEL_ROOT` remains available as an explicit override for an existing installation.

CSFD uses the existing dustmaps data directory when configured; otherwise setup configures a `dustmaps` subfolder under the DLYSO user-data directory. CSFD files are obtained from their original data provider rather than redistributed in the GitHub model archive.

Check the installation with:

```bash
dlyso-doctor --verify-models
```

For a private repository, model setup uses an authenticated GitHub CLI when anonymous download is unavailable. No tokens need to be pasted into DLYSO or its documentation. A public release can be downloaded without GitHub CLI.

## Release files

Each code version requires the matching release tag, currently `v1.1.0rc1`, containing `dlyso-models-1.1.0rc1.zip`. The checksum manifest is bundled with the Python package. Setup rejects missing, unexpected or corrupted model files.

Keep code, tests and documentation in Git. Upload the model archive as a release asset, not as Git source files. Public distribution still requires the [publication checklist](RELEASE_CHECKLIST.md). GitHub supports separate release assets; see [GitHub's release documentation](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).
