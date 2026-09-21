# Developer guide

## Layout

| Component | Responsibility |
|---|---|
| `dlyso.py` | CLI presets, input normalization, provenance and helper execution. |
| `dlyso_workflow.py` | Shared desktop/CLI task graph and channel dependencies. |
| `dlyso_engine.py` | Background workflow execution, streamed logs, cancellation and stage state. |
| `dlyso_ui.py` | Native Qt project, activity, results and guide screens. |
| `dlyso_runtime.py` | Atomic JSON writes, hashing, model paths and process-tree termination. |
| `dlyso_setup.py`, `install.py` | Automatic data installation and package/data bootstrap. |
| `dlyso_doctor.py` | Offline dependency/model inventory and checksum verification. |
| `scripts/` | Downloaders, representation generators, classifiers and combiner. |
| `docs/` | Editable Markdown documentation and verified desktop screenshots. |
| `dlyso_assets/` | Generated, installable offline documentation, example and model manifest. |
| `tests/` | Offline regression and desktop interaction tests. |
| `tools/` | Documentation rendering, screenshots, model smoke checks and release assembly. |

The GUI schedules work on a background Python thread and communicates through Qt signals. It never updates Qt widgets from a worker thread. Dependency-ready tasks use a thread pool; each helper remains a separate Python process. Only one inference task runs at a time. Failed tasks block their dependents without cancelling other channels. The combiner reads only channels completed in this attempt, writes atomically and signals the GUI to refresh results. POSIX workers start in their own session; cancellation terminates the whole session. On Windows, `taskkill /T` targets the launched process tree. The GUI stays responsive while stdout is drained continuously.

Desktop tests use Qt's offscreen platform. Runtime helpers can also be invoked directly, but top-level provenance protection applies only through the pipeline entry points.

## Run checks

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m dlyso_doctor --verify-models
python tools/check_models.py
# Optional small live end-to-end check (network access required):
python tools/smoke_pipeline.py examples/coordinates.csv --output /tmp/dlyso-smoke
QT_QPA_PLATFORM=offscreen python tools/capture_desktop.py
python tools/render_docs.py
python -m build
python tools/build_release.py
```

`check_models.py` is an explicit CPU smoke check of all supplied models with synthetic inputs. It does not report accuracy. It needs the model files and PyTorch. The ordinary tests use no network and do not require downloaded survey data. Tests of a representative ensemble parser import PyTorch/torchvision but do not load checkpoint weights.

The desktop screenshots use the shipped example for setup and synthetic, clearly labelled fixture data for results. They are generated from the actual widgets; no screenshot is a mock interface. Regenerate them after visual changes and inspect the images at normal and minimum window sizes.

The documentation renderer compiles the Markdown guides into one standalone HTML reference and synchronizes the installable resources. It embeds screenshot bytes, so the HTML has no external assets or required JavaScript. Markdown files remain the editing source of truth.

## Release assembly

`build_release.py` uses an explicit allowlist. It excludes project runs, private catalogues, environment files, temporary data and unrelated research outputs. It produces a source ZIP, a separate model ZIP and checksums. No upload, tag or public release is performed by the script.

The Python wheel excludes checkpoint binaries and includes the custom model configurations. Setup installs models in the versioned user-data directory. `DLYSO_MODEL_ROOT` remains an override for manually managed installations. Source installation remains the simplest route for research use.

The release candidate's exact local verification environment is recorded in `docs/VERIFICATION.md`; a constraints file captures the directly used dependency versions. These constraints describe that tested environment and are not a universal GPU/platform lockfile. Recheck PyTorch/Qt availability on every claimed target platform.

## Contribution conventions

Add regression tests for failures that can alter result integrity, repeatability or process control. Keep display code out of workflow planning. Do not infer completed data from the existence of a marker; inspect its status. Public archive requests ignore saved machine login settings; SED and ZTF failure markers also include request or parsing error details. Preserve original input rows and distinguish absent predictions from negative predictions.

Changes to model weights, preprocessing, matching or thresholds are scientific changes and should include a documented validation rationale. Preserve backward inspection of old results, but do not silently reuse incompatible cached processing artifacts.
