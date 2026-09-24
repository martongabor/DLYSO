# Output reference

## Project files

| Path | Contents |
|---|---|
| `project.json` | Desktop settings: input path, selected channels, batch sizes and version. |
| `run_manifest.json` | Normalized input path, input hash, software/model hashes, runtime versions and CLI parameters. |
| `run_state.json` | Stage states, start/end time and final run status. |
| `pipeline.log` | Activity log, appended across resumes. |
| `coords_normalized.csv` | Valid input rows with coordinate columns renamed to `ra` and `dec`. |
| `rejected_rows.csv` | Invalid rows, input record numbers and rejection reasons. |
| `SEDcsv/` | Filtered SED photometry named by coordinate pair. |
| `SEDplot/`, `SEDrplot/`, `AllWISE/`, `DTDM/` | Classifier input images. |
| `ZTFLC/` | Per-band ZTF light curves and attempt markers. |
| `ClassProbs/` | One ensemble probability CSV per channel. |
| `customClass/` | One custom probability CSV per channel and model family. |
| `result.csv` | Master input rows joined to model scores and channel coverage. |

`project.json` is produced by the desktop. Both the desktop and CLI `all` / `sed_classify` workflows write `run_state.json` and `pipeline.log`. Other CLI presets write the normalized input, rejected rows, manifest and stage outputs. A `.done` marker records an acquisition outcome; its existence alone does not establish success. Temporary `.part` files are not completed artifacts.

The run manifest records the latest top-level invocation. Preserve the whole folder and the software release for reproducibility. Remote archive content can change even when code and input hashes stay the same; the downloaded files are part of the scientific record.

## Result columns

`result.csv` updates as channels finish. Pending and failed channels have blank scores and `not_evaluated` coverage. Check `run_state.json` and the log to distinguish these cases from missing survey data.

The prefixes are `SEDplot`, `SEDrplot`, `AllWISE` and `DTDM`. For each selected channel, the combiner writes:

| Field | Type | Meaning |
|---|---|---|
| `<channel>_<architecture>` | Float in [0, 1], or blank | YSO-class model score for one of the ten architectures below. |
| `<channel>_custom_resnet` | Float in [0, 1], or blank | Custom SmallResNet sigmoid score. |
| `<channel>_custom_rca` | Float in [0, 1], or blank | Custom convolution/attention sigmoid score. |
| `<channel>_n_models` | Integer 0–12 | Number of non-missing model predictions. |
| `<channel>_status` | String | `complete`, `partial`, or `not_evaluated`. |
| `<channel>_votes` | Nullable integer 0–12 | Number of available models meeting their own threshold; blank if no models evaluated. |
| `<channel>_classification` | String or blank | `YSO` for at least 6 votes, `non-YSO` for fewer than 6, only when all 12 models evaluated; otherwise blank. |

Classification is assigned independently per channel using this default six-of-twelve rule. It is a convenient selection label, not confirmation of physical source type or a calibrated probability. It does not replace the model-specific score thresholds or other scientific selection rules in NGYSO I. Use the scores and votes to apply a different rule. The GUI shows the selected channel's label and exports all available channel labels. Legacy results gain labels from their stored votes when opened/exported.

Architectures: `efficientnet_b0`, `efficientnet_v2_s`, `mnasnet0_5`, `mobilenet_v3_small`, `regnet_y_400mf`, `resnet18`, `resnet50`, `resnext50_32x4d`, `shufflenet_v2_x0_5`, `squeezenet1_1`.

Examples:

| Models | Votes | Status | Interpretation |
|---|---|---|---|
| 12 | 0 | `complete` | Every model ran; none met its threshold. |
| 12 | 10 | `complete` | Ten of twelve models met their thresholds. |
| 2 | 2 | `partial` | Two available models met their thresholds; ten predictions are missing. |
| 0 | blank | `not_evaluated` | There is no model evidence for this channel. |

A vote fraction is not a posterior probability. The ensemble members can have correlated errors. No cross-channel fusion or calibrated final class label is generated.

## Joining and identity

The normalized catalogue is the master table. Prediction joins use RA and Dec rounded to six decimal places (default `--ndp 6` in the combiner). Multiple input rows at the same rounded position share predictions. Within a probability file, the first row for a duplicated rounded coordinate is kept. These joins are intended for artifacts generated from the same input, not for matching arbitrary catalogues.

Input metadata are preserved except for coordinate normalization and the reserved internal/output columns. Do not use `_ra_key`, `_dec_key`, `_input_row`, `_rejection_reason` or channel-prefixed prediction names for unrelated input metadata.

## Thresholds

The fixed thresholds below follow NGYSO I; see [Scientific context and citation](PAPER.md). A vote uses `score >= threshold`. The authors confirmed the AllWISE custom-model thresholds as SmallResNet **0.500** and RCA **0.580**. Earlier DLYSO versions interchanged these two values. The authors also confirmed the SEDr SqueezeNet threshold as **0.577**, correcting the earlier value of 0.757. Recombine saved predictions to correct existing AllWISE and SEDr vote totals; model inference does not need to be repeated. Editing thresholds changes the scientific decision rule and requires validation.

<!-- THRESHOLDS_START -->
| Model | SED | Dust-aware SED | AllWISE | DTDM |
|---|---:|---:|---:|---:|
| `efficientnet_b0` | 0.383 | 0.898 | 0.454 | 0.585 |
| `efficientnet_v2_s` | 0.508 | 0.493 | 0.720 | 0.334 |
| `mnasnet0_5` | 0.265 | 0.938 | 0.553 | 0.490 |
| `mobilenet_v3_small` | 0.598 | 0.857 | 0.477 | 0.477 |
| `regnet_y_400mf` | 0.655 | 0.558 | 0.486 | 0.489 |
| `resnet18` | 0.598 | 0.653 | 0.503 | 0.545 |
| `resnet50` | 0.484 | 0.801 | 0.501 | 0.553 |
| `resnext50_32x4d` | 0.457 | 0.617 | 0.470 | 0.519 |
| `shufflenet_v2_x0_5` | 0.402 | 0.757 | 0.596 | 0.408 |
| `squeezenet1_1` | 0.194 | 0.577 | 0.365 | 0.482 |
| `custom_resnet` | 0.470 | 0.650 | 0.500 | 0.480 |
| `custom_rca` | 0.650 | 0.710 | 0.580 | 0.500 |
<!-- THRESHOLDS_END -->
