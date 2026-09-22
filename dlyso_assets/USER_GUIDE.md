# DLYSO user guide

DLYSO classifies candidate young stellar objects (YSOs) using survey photometry, images and light curves. It takes a catalogue of coordinates and saves individual model scores. Scores require scientific validation before use for source selection.

## Installation

To install directly from a repository, see [GitHub installation](GITHUB_INSTALL.md). The instructions below use a local source folder.

### 1. Prepare Python

Use Python 3.10 or newer and a virtual environment. Run these commands inside the DLYSO source folder:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[gui]"
```

Windows activation is `.venv\Scripts\activate`. For command-line use without the desktop toolkit, install with `python -m pip install -e .` instead. The CLI and desktop use the same interpreter and model files. The desktop is built with Qt for Python, not a browser server.

### 2. Install models and dust maps

Run:

```bash
dlyso-setup
```

This downloads the 48 model files from the matching GitHub Release, checks their SHA-256 hashes and puts them in DLYSO's user-data directory. The app locates them automatically. It also downloads missing CSFD maps through dustmaps. No manual ZIP extraction is needed.

For a source checkout, `python install.py` performs both the Python installation and data setup. See [GitHub installation](GITHUB_INSTALL.md) for private-repository access, storage locations and complete commands.

### 3. Check the installation

```bash
python -m dlyso_doctor --verify-models
```

The model download is about 1.4 GiB; allow additional space for unpacking, CSFD maps and Python dependencies. `dlyso-setup --skip-dust` omits dust maps if the dust-aware SED channel is not needed. Running setup again reuses verified models and existing maps.

The doctor checks Python modules and model hashes without network access. It does not certify scientific accuracy or GPU compatibility. `DLYSO_MODEL_ROOT` remains supported for manually managed model installations.

### 4. Launch

```bash
python dlyso_ui.py
```

After installation the `dlyso-gui` command also launches the desktop. The application uses a consistent light palette, including when macOS Dark Mode is enabled. Linux requires a graphical desktop and Qt platform libraries. Remote servers can use the command line.

## Create a project

1. In **Project**, choose **Use the example catalogue**. The catalogue includes additional sources with verified public ZTF light curves; see **Example catalogue** below.
2. Enter a short project name. Names start with a letter or digit and accept letters, digits, dots, underscores and hyphens, up to 80 characters.
3. Choose the parent projects folder. DLYSO creates one subfolder for the project.
4. Keep **Spectral energy distribution** selected. This first run needs network access and SED models, but no account or dust maps.
5. Keep classification enabled to produce `result.csv`. Disable it if you only want downloaded data and derived images.
6. Click **Start project**. Input validation runs before downloads. The **Activity** page shows waiting, running, complete, failed, blocked and cancelled stages.
7. Once a channel finishes, click **View results**. Review how many sources were evaluated before interpreting votes.

The app starts with four download workers per branch and an inference batch of 16. A batch is the number of images sent to a model at once. If you run out of memory, reduce it; a batch of 1 is valid. Increasing workers increases concurrent requests, not necessarily throughput. Independent branches can each use the configured number of workers.

## Example catalogue

The bundled catalogue contains 13 positions: the original two demonstration inputs and 11 additional named sources with public ZTF light curves downloaded successfully on 2026-09-22. Choose **Use the example catalogue** and enable **ZTF light curves** to try them. Use a new project name for this expanded catalogue.

Coordinates for the added sources come from the [CDS Sesame/SIMBAD resolver](https://cds.unistra.fr/cgi-bin/Sesame). Verification used DLYSO's downloader with its default 2-arcsecond search radius and dominant object ID per band, followed by DTDM rendering. The table counts points retained by the current DTDM cuts (`catflags == 0`, non-missing MJD and magnitude). Zero means no usable downloaded points in that band.

| Source | g points | r points | i points |
|---|---:|---:|---:|
| BP Tau | 411 | 0 | 0 |
| CI Tau | 396 | 0 | 0 |
| DL Tau | 409 | 358 | 0 |
| DR Tau | 30 | 0 | 0 |
| DN Tau | 71 | 0 | 0 |
| DO Tau | 75 | 93 | 0 |
| GM Aur | 411 | 0 | 0 |
| V409 Tau | 421 | 803 | 0 |
| V836 Tau | 380 | 447 | 0 |
| VY Tau | 420 | 667 | 14 |
| IQ Tau | 72 | 130 | 22 |

All added sources produced nonempty DTDM images. These are workflow examples, not a labelled accuracy benchmark or independent validation sample. The original two rows have not been included in this ZTF check. Archive availability and counts can change; the [IRSA API](https://irsa.ipac.caltech.edu/docs/program_interface/ztf_lightcurve_api.html) uses the latest public collection by default. Download URLs, object IDs and measurement counts are recorded in `examples/ztf_verification.csv` in the repository. Light curves are downloaded when the project runs, rather than bundled with the application.

## Prepare your catalogue

The input is a comma-separated text file with one header row. Coordinates must be **ICRS decimal degrees**, not sexagesimal strings, Galactic longitude/latitude or radians.

| Quantity | Accepted column names, case-insensitive | Valid values |
|---|---|---|
| Right ascension | `ra`, `RAJ2000`, `_RA`, `ra_icrs`, `_ra_icrs` | Finite, 0 ≤ RA < 360 |
| Declination | `dec`, `DEJ2000`, `_DE`, `de_icrs`, `_de_icrs` | Finite, −90 ≤ Dec ≤ 90 |

Use one coordinate pair. Include a stable `source_id` for readable results. Other columns are preserved; avoid names starting with a modality prefix such as `SEDplot_`, which DLYSO reserves for predictions.

Rows with invalid or missing coordinates go to `rejected_rows.csv`, with the input CSV record number (header is record 1) and a reason. They are excluded from `coords_normalized.csv` and final predictions. A catalogue with no valid rows stops before network work. Duplicate coordinates remain separate master rows but share acquired data and predictions. Matching uses coordinates rounded to six decimal places; it is not a general-purpose crossmatch.

## Data channels

**Spectral energy distribution.** Retrieves VizieR SED measurements within a default radius of 2 arcsec, applies the fixed catalogue/filter rules and renders a log–log SED. A plot needs more than nine occupied wavelength bins. A source may have measurements but still lack a usable plot.

**Dust-aware SED.** Uses the same SED data and a CSFD-derived background. It requires local CSFD maps. This is a contextual dust feature, not a fitted distance-dependent extinction correction.

**AllWISE images.** Retrieves a 200 × 200 pixel AllWISE colour cutout over a 30 arcsec field. The image-quality check rejects some cutouts. These are recorded as `REJECTED`, leave the source unevaluated in AllWISE, and do not stop the other channels. Archive request failures remain errors.

**ZTF light curves.** Retrieves ZTF light curves and produces an RGB time-difference/magnitude-difference (DTDM) image. Each band needs at least five quality-selected measurements. The current acquisition rule skips declinations at or below −30°. DLYSO downloads the API's default public collection anonymously. Proprietary collections are outside its scope. See the [IRSA API reference](https://irsa.ipac.caltech.edu/docs/program_interface/ztf_lightcurve_api.html).

The two SED channels share one download step, then render independently. Each representation unlocks its own custom and ensemble classifiers immediately: SED classification does not wait for dust-aware SED plots, AllWISE or ZTF. Ready classifier jobs share a single inference slot to limit GPU memory use; downloads and plotting continue alongside inference. The result table and Results page refresh after each channel finishes. Pending or failed channels remain `not_evaluated`, and predictions from an earlier attempt are excluded until that channel finishes successfully in the current run. This scheduling also applies to CLI `all` and `sed_classify`.

## Read the Activity page

Activity shows one progress bar per selected modality. Each bar advances as stages finish: validation, acquisition, image generation (where needed), and custom and ensemble classification. The label shows the current operation. Shared SED acquisition advances both SED bars. Bars count completed stages, not elapsed time or source coverage; classifier details and download counts remain in the log. A failed or stopped channel keeps its completed progress. Result coverage is calculated separately from predictions.

The live log reports download summaries and classifier messages. The full log is saved to `pipeline.log`. The on-screen buffer retains the most recent 5,000 lines; **Save log** exports the complete saved log when available.

A transient HTTP failure is retried within the bounded HTTP request policy. VizieR can also return truncated XML with a successful HTTP status. SED acquisition validates each response and makes up to three attempts using equivalent coordinate query encodings; coordinates, precision and search radius remain unchanged. The activity log and failed-target markers include the target and actual error. ZTF also logs each requested target, completed-target progress, and any error message returned by IRSA. Incomplete responses are never used for classification. If targets still fail, that download stage is marked failed and its dependent stages are blocked. Independent channels keep running and publish their results. A run with successful classifications and channel errors ends as `partial`, with the errors visible in Activity and `run_state.json`; it is not reported as successful. The CLI returns a nonzero exit status in this case. Successfully downloaded artifacts remain available to resume.

## Stop and resume

Click **Stop run** to terminate the active process trees. DLYSO first requests termination, then escalates for lingering processes. No new stage is scheduled after cancellation. Closing the window during a run asks whether to stop it.

To resume, open the project, keep its original input catalogue and start it again. Confirm reuse of the existing artifacts. Failed SED placeholders and failed ZTF markers are retried; completed data are reused. AllWISE quality rejections are also retained; the downloader's `--retry-rejected` option explicitly requests those cutouts again. Atomic download writes prevent partial files from becoming completed artifacts.

A project fingerprint ties the run to the original input bytes, processing code and model files. Changing them requires a new project folder. Even a harmless edit to the original CSV changes its fingerprint. Legacy projects without fingerprints can be inspected, but should be rerun in a new folder.

Do not run two DLYSO instances against the same project folder at the same time. Keep a copy of the entire project for an important analysis.

## Inspect Results

Open an existing project or view results as each channel finishes. Select a channel from the dropdown. The top counters show the entire catalogue's coverage for that channel, even while a text search filters visible rows.

- **Source** uses `source_id` when available, with common name/ID alternatives and a generated label as a fallback.
- **Votes** counts individual models whose score meets their own fixed threshold. A blank value means no model evaluated the source.
- **Models** is the number of available predictions, from 0 to 12.
- **Coverage** is Complete (12), Partial (1–11) or Not evaluated (0).

Click a row to see its input image and all individual scores. Missing images and scores are shown explicitly. Table headers support sorting; the search box matches source labels, coordinates and displayed values. **Export CSV** exports the full catalogue, including columns not displayed in the browser; it does not export only the filtered rows.

When opening a legacy result file, the browser corrects the view and exports so missing predictions are not shown as zero votes. It does not rewrite the original file on disk.

Compare votes only alongside model availability. Ten votes out of twelve and two votes out of two are different situations. Neither is a calibrated probability of being a YSO. Detailed field definitions are in the Output reference.

## Troubleshooting

| Symptom | Meaning and next step |
|---|---|
| No valid coordinates | Inspect `rejected_rows.csv`; convert coordinates to ICRS decimal degrees. |
| Model file missing or hash mismatch | Run `dlyso-setup`, check any `DLYSO_MODEL_ROOT` override, and rerun the doctor. |
| Dust-aware stage fails | Run `dlyso-setup` without `--skip-dust` in the active Python environment. |
| Download stage fails | Check connectivity or archive availability, then resume the same project. Repeated failures remain errors, not negative classifications. |
| ZTF has no usable image | Check sky coverage, band availability and the five-measurement minimum; empty data can be a legitimate outcome. |
| Few SED images | Inspect SED filtering and the requirement for more than nine occupied wavelength bins. |
| GPU or memory error | Reduce inference batch size. For CPU diagnostics, run the individual classifiers with `--device cpu`. |
| Different input/software/model warning | Create a new project folder; do not delete provenance to bypass the check. |
| Blank votes | No prediction exists for that source/channel. Check coverage and the acquisition artifacts. |
| Desktop will not start | Install the `gui` extra, launch from the correct environment and check the Qt display/platform error in a terminal. |

For a useful bug report include the software version, OS, Python version, selected channels, the relevant sanitized log excerpt and a minimal non-sensitive input example. Do not include private catalogues by default.
