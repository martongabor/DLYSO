# Model card

## Scope and intended use

DLYSO runs image classifiers for four types of YSO data and saves each model score. Intended users are researchers who can inspect data quality, validate results against labelled data and document sample selection.

The scientific method and evaluation are described in Marton et al. (2026), NGYSO I, accepted for publication in Astronomy & Astrophysics; see [Scientific context and citation](PAPER.md). The paper documents training samples, source-level train/validation/test separation, training procedures, validation-selected thresholds and test-set performance. This software release contains inference artifacts, not the full training and evaluation workflow. Software smoke tests demonstrate that weights load and numerical predictions can be produced; they do not independently reproduce the paper's accuracy, completeness or false-positive-rate measurements.

## Supplied models

- Ten torchvision CNN architectures for each of four channels: 40 checkpoints.
- Custom SmallResNet and ResConvAttnClassifier for each channel: eight checkpoints.
- Custom JSON configurations specify architecture, class mapping and preprocessing.
- A SHA-256 manifest identifies the exact 48 weight files in this release.

The ensemble loader reads class order and image size from checkpoint metadata, loads weights strictly and uses softmax for the YSO score. Custom models use their JSON preprocessing configuration and a sigmoid output. RGB inputs are resized for ensemble inference; the custom model configurations may use grayscale conversion. There is no retraining, test-time augmentation or learned cross-channel fusion in the pipeline.

## Representation assumptions

SEDs use fixed catalogue exclusions, survey-provenance rules, frequency deduplication, wavelength binning, plotting limits and a minimum number of occupied bins. Multiple values within a wavelength bin overwrite one another according to the existing rendering rule. The rendered SED is not a physical SED fit and does not propagate full photometric uncertainties into predictions.

Dust-aware images encode a CSFD dust value in the image background. This is a contextual feature and can introduce dependence on sky position and environment. AllWISE inputs are archive colour renderings, not calibrated pixel-level flux measurements. DTDM images encode pairwise time and magnitude differences after fixed quality cuts. Their appearance depends on cadence, sample size and band availability.

These representations should be kept consistent with model training. The release preserves the supplied preprocessing rules and checkpoint configurations. Their equivalence to every training-time transformation described in NGYSO I has not been independently audited.

## Published-method context and release reproducibility

NGYSO I describes the KYSO and NEMESIS Orion YSO samples, the non-YSO comparison samples, source-level data splitting, network training and validation-based threshold selection. Its ordinary-SED ensemble reports 96.36% YSO recovery and a 0.43% non-YSO false-positive rate on the paper's test set. Those results should be cited as findings of the paper, not as fresh measurements from this repository's software checks.

Reproducing that evaluation from this release alone still requires the exact catalogue snapshots and split membership, the complete training/evaluation code and run configurations, and a mapping from the released checkpoint hashes to the evaluated models. Generalisation to new sky regions or survey selections and probability calibration require separate assessment. Model ownership and redistribution terms also remain to be documented.

The fixed thresholds are disclosed in the output reference; their presence is not evidence of probability calibration.

## Suggested validation protocol

Before publishing a candidate catalogue, freeze the release/model hashes and define a labelled evaluation sample independent of training and threshold selection. Report evaluation coverage alongside performance; sources without usable inputs must not silently disappear from the denominator. Evaluate each channel and the intended selection rule separately. Test geographic and survey-domain shifts, and inspect false positives and false negatives.

Report uncertainty on performance estimates and compare against suitable catalogue/photometric baselines. If a combined decision rule is introduced later, validate that rule on data not used to choose it. Keep raw survey artifacts, normalized coordinates and selection code with the analysis record.

## Limitations

A high score can reflect correlations in the training sample rather than youth. Missing or blended photometry, survey rendering differences, extinction, cadence and training-set overlap may change behavior. Agreement among architectures does not guarantee independent evidence. Scientific performance claims should identify the NGYSO I evaluation sample and selection rule; the released inference workflow has not independently reproduced the complete paper analysis.
