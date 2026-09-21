# DLYSO

Software for young stellar object classification.

DLYSO downloads photometry, AllWISE images and ZTF light curves for a catalogue of sky coordinates. It creates input images, runs the classifiers and saves per-source model scores. The GUI provides project settings, an activity log and a results table.

![DLYSO project settings](docs/images/project.png)

**Release candidate: 1.1.0rc1.** The software includes regression tests and installation checks. Scientific performance is not established by those checks; see the [model card](docs/MODEL_CARD.md). Author, license and model redistribution metadata must be finalized before public distribution.

## Installation

Install the version published in [martongabor/DLYSO](https://github.com/martongabor/DLYSO):

```bash
python -m pip install "dlyso-pipeline[gui] @ git+https://github.com/martongabor/DLYSO.git"
dlyso-setup
dlyso-gui
```

Models and CSFD maps are downloaded automatically by `dlyso-setup`; see the [GitHub installation guide](docs/GITHUB_INSTALL.md). The source installation instructions follow.

Use Python 3.10 or newer in a virtual environment. Python 3.11 is a practical default; the local release checks record their exact interpreter and dependency versions.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[gui]"
dlyso-setup
python -m dlyso_doctor --verify-models
python dlyso_ui.py
```

On Windows, activate with `.venv\Scripts\activate`. On Linux, a working desktop/display session is required for the GUI; the CLI works without one.

Run `dlyso-setup` to download and verify all 48 model files and any missing CSFD maps. No manual ZIP extraction or model-path setting is needed. From a source checkout, `python install.py` installs the Python package and data in one step. [Installation details](docs/GITHUB_INSTALL.md)

In the app:

1. Click **Use the example catalogue**, or browse to your own CSV.
2. Choose a project name and destination. Leave **Spectral energy distribution** selected for a first run.
3. Click **Start project**. The Activity page shows actual stage states and saves a log.
4. Open **Results** to inspect images, individual scores and missing-data coverage.

Archive services are contacted during a run. Opening existing results and reading the guide work offline.

## Data channels

| Channel | Data | Additional requirement |
|---|---|---|
| Spectral energy distribution | VizieR SED photometry | Network access |
| Dust-aware SED | SED photometry + CSFD dust background | Local CSFD maps |
| AllWISE images | AllWISE colour cutouts | Network access |
| ZTF light curves | ZTF light curves → DTDM images | Network access |

Each eligible source has up to **12 model scores per channel**: ten torchvision architectures and two custom models. These are separate predictions. DLYSO does not claim a calibrated, combined probability across channels.

## Input and output

```csv
source_id,ra,dec
candidate-001,277.448097,-10.562957
candidate-002,83.822083,-5.391111
```

Coordinates are ICRS decimal degrees. Invalid rows are recorded in `rejected_rows.csv`; valid input columns are retained. The final `result.csv` includes each model score, a vote count, the number of models evaluated and a coverage status. **No data means `not_evaluated` and blank votes, never zero votes.**

![DLYSO results browser](docs/images/results.png)

## Command line

```bash
# Validate without contacting archive services
python dlyso.py examples/coordinates.csv --runroot runs/first-check --steps preflight

# Download AllWISE images only
python dlyso.py examples/coordinates.csv --runroot runs/infrared --steps allwise --workers 4

# See all stage presets and parameters
python dlyso.py --help
```

Each channel starts classification as soon as its representation is ready, independently of slower downloads. Failed channels do not cancel healthy ones; results appear incrementally. The desktop supports arbitrary channel combinations. CLI `all` selects all four channels, including dust-aware SEDs; install CSFD maps first. CLI `sed_classify` also includes the dust-aware channel. [CLI reference →](docs/CLI_REFERENCE.md)

## Documentation

- [User guide](docs/USER_GUIDE.md) — installation, first project, resuming, results and troubleshooting.
- [Output reference](docs/OUTPUT_SCHEMA.md) — field definitions, missingness and thresholds.
- [Model card](docs/MODEL_CARD.md) — preprocessing, intended use and scientific limitations.
- [Developer guide](docs/DEVELOPMENT.md) — architecture, checks and release assembly.
- [Release checklist](docs/RELEASE_CHECKLIST.md) — remaining publication metadata and validation gates.
- [Offline reference](dlyso_pipeline_docs.html) — the complete guide in one searchable, self-contained file.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python tools/render_docs.py
python tools/build_release.py
```

Tests use synthetic inputs and mocked network failures. Full inference and archive access have separate opt-in smoke checks. The unrelated Local Bubble visualization and filter-analysis scripts remain in the working folder; they are outside the DLYSO software release.
