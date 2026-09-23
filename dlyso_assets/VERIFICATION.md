# Verification record

Local release-candidate checks performed on 14–23 September 2026. This records software behavior, not a scientific benchmark.

## Environment

- macOS 26.5.2, Apple Silicon (arm64).
- Python 3.11.14; Qt for Python / PySide6 6.9.2.
- PyTorch 2.10.0 and torchvision 0.25.0; numerical smoke checks used CPU.
- NumPy 1.26.4, pandas 3.0.2, Astropy 7.2.0, dustmaps 1.0.14.
- astroquery 0.4.12.dev10784 was present locally. This development version is recorded explicitly and is not pinned as a required public PyPI release.
- pytest 8.4.2 and Ruff 0.14.14.

`constraints-tested.txt` records the directly used package versions, with the development build commented. The package requirements allow compatible releases; an isolated fresh dependency-resolution matrix has not been exercised locally.

## Results

| Check | Outcome |
|---|---|
| Offline regression and desktop interaction suite | 51 tests passed. |
| Mixed-precision output export | CPU regression tests feed bfloat16, float16 and float32 logits through the actual ensemble inference and CSV-export path, verifying per-model probabilities and their mean. This checks dtype handling, not physical CUDA or MPS execution. |
| AllWISE rejection regression | Verified a cached 186-source stage completes with 183 reused images and three nonfatal quality rejections; network failures remain fatal and retryable. |
| Independent scheduling | Offline subprocess tests verify inference before an unrelated download finishes, failure isolation, serialized inference, partial result publication, exclusion of stale predictions, GUI refresh and CLI parameter forwarding. No new live four-channel or GPU certification is claimed. |
| Ruff lint | Passed for the DLYSO release scope. Unrelated astronomy scripts are excluded. |
| Model inventory and SHA-256 verification | 48 of 48 model files match the release manifest. |
| CPU model smoke check | All 48 checkpoints load strictly and produce finite outputs on synthetic tensors. |
| Anonymous ZTF API request | HTTP 200; 728 measurements, no authorization header or cookies. |
| Live VizieR SED requests | Demonstration source succeeded. Recovered five failed targets in a 186-source catalogue, including three persistently truncated XML responses recovered through equivalent coordinate query encodings; all 186 SED CSV files available. |
| Full catalogue attempt | Both SED plot stages produced 186 images. ZTF acquisition encountered HTTP 400 archive errors and timeouts; that attempt was stopped before classification. This does not establish a successful full four-channel run. |
| Ordinary-SED workflow | The downloaded source passed plotting, both custom classifiers, ten ensemble models and the final join; coverage is complete with 12 model predictions. |
| Desktop rendering | Simplified page headings inspected on all four pages; project/results screenshots refreshed at 1370 × 920 and minimum-window layout checked at 1120 × 760. |
| Modality progress | Four selected modalities produce four bars; shared SED acquisition, both classifier stages, channel failure and cancellation are covered by offscreen tests. |
| Automatic data setup | Offline tests cover verified extraction, reuse, corrupt archives, unsafe archive paths and interrupted downloads. A fresh setup using the private GitHub Release downloaded, extracted and verified all 48 checkpoints. Existing CSFD maps were checked; a new CSFD network download was not repeated. |
| In-app documentation | Relative GitHub installation link loads Markdown content; Back returns to the user guide. |
| Git installation | pip installation from a temporary local Git repository and the private GitHub v1.1.0rc1 tag passed. Installed GUI documentation and all modality model paths were checked outside the checkout. Dependencies were reused from the tested environment; this is not a fresh dependency-resolution test. |
| Python wheel | Built and installed into a separate target directory; the installed GUI, guide, example, model checksum check and CLI preflight passed. Weights are excluded. |
| Release contents | Source archive verified to exclude runs, environment files, private catalogues and unrelated research outputs; model archive contains exactly 48 checkpoints in the documented layout. |
| Offline HTML reference | Local Markdown links and HTML anchors checked; bundled documentation matches the source guides. Two updated screenshots embedded. |

The first sandboxed live request was blocked by network restrictions; it succeeded when explicitly allowed outside the sandbox. The first end-to-end inference attempt was blocked by PyTorch shared-memory process restrictions; the same one-source CPU workflow succeeded outside that sandbox. These were environment restrictions, not silently suppressed successful checks.

Screenshots under `docs/images/` show the current 11-source public example catalogue and its actual completed CPU ZTF/DTDM classification run (2026-09-22). All 12 DTDM classifiers were run on the downloaded public light curves. Project, results, activity and minimum-size images were regenerated from current Qt widgets. `docs/screenshot-provenance.json` records the inputs and result checksum. No private catalogue is included in release documentation or archives.

## Limits

- The complete four-channel workflow was not run. Live AllWISE and local CSFD integration still need service-specific checks in the publishing environment. A separate anonymous ZTF API request returned HTTP 200 and 728 measurements without authorization headers or cookies; this checks archive access, not the full DTDM workflow.
- CUDA and MPS end-to-end execution were not certified by this CPU validation.
- Native Windows and Linux desktop behavior was not tested locally. The included GitHub Actions workflow defines Linux offline checks but has not been run on a remote repository in this session.
- A browser automation surface was unavailable for an interactive HTML-reference check. The generated document's structure, embedded assets and internal navigation are checked locally; desktop Qt screens were visually inspected.
- No independent labelled evaluation data were supplied. Accuracy, contamination, completeness and calibration remain unmeasured here.
- Authorship, code license, model redistribution rights and public repository/citation metadata remain maintainer decisions.
