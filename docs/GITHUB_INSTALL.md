# GitHub installation

### 1. Choose a Python environment

Use Python 3.10 or newer and Git. A virtual environment keeps DLYSO's Python dependencies separate from other software. It is recommended, but it is not a second installation method. If you already have a suitable environment (for example, a dedicated conda environment), activate it and continue to step 2.

To create a new environment, run this once in a folder where you want to keep it:

```bash
python -m venv .venv
```

Then activate it using the command for your shell:

| Shell | Activation command |
|---|---|
| macOS / Linux (bash or zsh) | `source .venv/bin/activate` |
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows Command Prompt | `.venv\Scripts\activate.bat` |

If your system provides `python3` instead of `python`, use `python3` for the environment-creation command. The commands below use `python` inside the activated environment.

### 2. Install DLYSO and its data once

For access to a private repository, sign in with GitHub CLI (`gh auth login`) and configure Git access (`gh auth setup-git`) first.

Run these two commands in your chosen environment. No source-folder download or clone is needed:

```bash
python -m pip install "dlyso-pipeline[gui] @ git+https://github.com/martongabor/DLYSO.git"
dlyso-setup
```

The first command installs the application and Python dependencies. The second downloads and verifies all 48 models and any missing CSFD dust maps, placing them where DLYSO finds them automatically. No manual ZIP extraction is needed. Use `dlyso-setup --skip-dust` if you do not need the dust-aware SED channel.

### 3. Start the GUI

```bash
dlyso-gui
```

In a new terminal, activate the same environment before starting DLYSO. You do not need to recreate the environment or reinstall the application each time. If you already installed DLYSO successfully in an existing environment, keep using that environment; these instructions do not require a second installation.

## Linux requirements

The GUI needs a graphical desktop session. On Ubuntu/Debian, install the Qt system libraries:

```bash
sudo apt-get update
sudo apt-get install -y libegl1 libopengl0
```

The CLI works without a graphical desktop.

## Download size and installation check

The models total about 1.4 GiB. Allow about 3 GiB of temporary space for downloading and unpacking them, plus space for CSFD maps and Python dependencies. Repeating `dlyso-setup` verifies and reuses installed files. If a download fails, run it again; partial archives are discarded.

```bash
dlyso-doctor --verify-models
```

The doctor checks dependencies and model files, not scientific accuracy or GPU compatibility.

## Alternative: install from a source checkout

Use this route if you want a local copy of the source code. Choose this route **instead of step 2 above**, not in addition to it. First choose and activate your Python environment as described in step 1.

```bash
git clone https://github.com/martongabor/DLYSO.git
cd DLYSO
python install.py
```

`python install.py` installs both the application and its data. Then launch with `dlyso-gui` as in step 3. The installer also accepts `--skip-dust`.

For development, use `python -m pip install -e ".[dev]"` followed by `dlyso-setup` from the checkout. Editable installation is for working on the code, not a required step for GUI users.

For a fixed code version, append an existing tag or full commit hash after `.git` in the pip command. See [pip's Git installation reference](https://pip.pypa.io/en/stable/topics/vcs-support/).

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
