# Command-line reference

Run `python dlyso.py --help` for the authoritative argument list. Installed entry points are `dlyso`, `dlyso-gui`, `dlyso-doctor` and `dlyso-setup`.

## Stage presets

| `--steps` | Work performed |
|---|---|
| `preflight` | Validate and normalize coordinates; write rejected rows and provenance. No network requests. |
| `sed` | Download SED CSVs. |
| `allwise` | Download AllWISE cutouts. |
| `ztflc` | Download public ZTF light curves. |
| `downloads` | Run SED, AllWISE and ZTF acquisition. |
| `plots` | Create both ordinary and dust-aware SED images from existing SED CSVs. |
| `dtdm` | Create DTDM images from existing light curves. |
| `classify` | Run custom and ensemble classifiers for all four channels. |
| `combine` | Join existing probabilities to the normalized input. |
| `sed_classify` | Download SEDs, render both SED image variants, classify both and combine. Requires CSFD maps. |
| `all` | Complete four-channel workflow; default when `--steps` is omitted. Requires CSFD maps. |

Use the GUI for arbitrary channel combinations, such as ordinary SEDs without dust-aware SEDs. A preflight run creates the standard output directories, even if some are unused.

## Common options

| Option | Default | Meaning |
|---|---|---|
| positional input CSV | required | Original source catalogue. |
| `--runroot` | `myrun` | Project output directory. |
| `--workers` | 16 | Concurrent acquisition workers per downloader. Start with 4 for small runs. |
| `--radius` | 2.0 | SED query radius in arcsec; does not change AllWISE or ZTF query geometry. |
| `--custom-batch` | 128 | Custom-model inference batch size. |
| `--class-batch` | 128 | Ensemble inference batch size. |
| `--dtdm-workers` | preset-dependent | Number of DTDM processing workers. |
| `--verbose` | off | Stream helper output for selective presets. `all` and `sed_classify` always stream output. |
| `--version` | — | Print software version and exit. |

For `all`, DTDM workers default to `--workers`; the standalone `dtdm` preset uses the helper default unless overridden.

Both batch sizes must be positive. The desktop uses smaller defaults (16) to reduce initial memory demand. Smaller batches change resource use, not the set of intended predictions.

## Examples

```bash
python dlyso.py examples/coordinates.csv --runroot runs/check --steps preflight
python dlyso.py examples/coordinates.csv --runroot runs/wise --steps allwise --workers 4
python dlyso.py examples/coordinates.csv --runroot runs/full --steps all --workers 4 --custom-batch 16 --class-batch 16
```

ZTF requests use the default public archive collection. The CLI has no account or login options.

The CLI uses automatic device selection: CUDA, then Apple MPS, then CPU. Individual classifier helpers accept `--device cpu` for diagnostics:

```bash
python scripts/class.py --runroot runs/full --types SEDplot --device cpu --batch-size 4 --num-workers 0
python scripts/customclass.py --runroot runs/full --folders SEDplot --device cpu --batch-size 4
```

When invoking helpers directly, pass explicit output paths if the defaults are unsuitable. Direct helper invocations do not provide the top-level input/provenance guard.

## Exit behavior

Invalid configuration and unrecovered download/classification errors return a nonzero exit status. Missing survey coverage is distinct from a request failure: it may result in no image and a `not_evaluated` result. Keep stderr and stdout in automated jobs. The desktop saves both to its project activity log.

## Retry rejected AllWISE cutouts

An image-quality rejection is missing evidence, not a fatal network error. Rejected cutouts are normally reused as missing data on resume. To request them again explicitly:

```bash
python scripts/getstamp.py --input-csv runs/full/coords_normalized.csv --outdir runs/full/AllWISE --retry-rejected
```

The existing cutout-quality rule remains unchanged. Successful images are reused; real request failures still return a nonzero exit status.

## Independent channel scheduling

`all` and `sed_classify` render and classify each channel as soon as its dependencies finish. SED acquisition is shared; its two plot types are separate tasks. Inference runs one classifier job at a time, alongside acquisition and plotting. `result.csv` is updated atomically as channels complete. Failed channels do not cancel healthy ones; partial runs retain results and return a nonzero exit status. Selective helper presets retain their existing behavior.

## Data installation

`dlyso-setup` downloads and verifies models, installs them to a user-writable directory, and downloads missing CSFD maps. `--skip-dust` installs only the models. `python install.py` combines package installation and data setup from a source checkout. Neither command downloads source-specific survey observations; those are acquired when a project runs.
