# Model card

## Scope and intended use

DLYSO runs image classifiers for four types of YSO data and saves each model score. Intended users are researchers who can inspect data quality, validate results against labelled data and document sample selection.

This release contains inference artifacts. It does not contain a documented training pipeline or a benchmark establishing performance on an independent sample. Software smoke tests demonstrate that weights load and numerical predictions can be produced; they do not measure accuracy, completeness, contamination or calibration.

## Supplied models

- Ten torchvision CNN architectures for each of four channels: 40 checkpoints.
- Custom SmallResNet and ResConvAttnClassifier for each channel: eight checkpoints.
- Custom JSON configurations specify architecture, class mapping and preprocessing.
- A SHA-256 manifest identifies the exact 48 weight files in this release.

The ensemble loader reads class order and image size from checkpoint metadata, loads weights strictly and uses softmax for the YSO score. Custom models use their JSON preprocessing configuration and a sigmoid output. RGB inputs are resized for ensemble inference; the custom model configurations may use grayscale conversion. There is no retraining, test-time augmentation or learned cross-channel fusion in the pipeline.

## Representation assumptions

SEDs use fixed catalogue exclusions, survey-provenance rules, frequency deduplication, wavelength binning, plotting limits and a minimum number of occupied bins. Multiple values within a wavelength bin overwrite one another according to the existing rendering rule. The rendered SED is not a physical SED fit and does not propagate full photometric uncertainties into predictions.

Dust-aware images encode a CSFD dust value in the image background. This is a contextual feature and can introduce dependence on sky position and environment. AllWISE inputs are archive colour renderings, not calibrated pixel-level flux measurements. DTDM images encode pairwise time and magnitude differences after fixed quality cuts. Their appearance depends on cadence, sample size and band availability.

These representations should be kept consistent with model training. The release preserves the supplied preprocessing rules; it does not assert that the undocumented training preprocessing has been independently reconstructed and verified.

## Evidence not supplied

The following information must be supplied by the model authors before making quantitative scientific performance claims:

- Training and validation catalogue names, versions, labels and source selection.
- Split construction, including source, region and survey overlap controls.
- Training objectives, hyperparameters, random seeds and checkpoint selection.
- Threshold-selection data and criteria.
- Independent test-set results, confusion matrices and precision–recall curves.
- Score calibration and performance stratified by sky region, extinction, brightness, missing bands and crowding.
- Rights and licenses covering redistribution of each checkpoint and its training data.

No values are substituted for missing evidence. The fixed thresholds are disclosed in the output reference, but their presence is not evidence of calibration.

## Suggested validation protocol

Before publishing a candidate catalogue, freeze the release/model hashes and define a labelled evaluation sample independent of training and threshold selection. Report evaluation coverage alongside performance; sources without usable inputs must not silently disappear from the denominator. Evaluate each channel and the intended selection rule separately. Test geographic and survey-domain shifts, and inspect false positives and false negatives.

Report uncertainty on performance estimates and compare against suitable catalogue/photometric baselines. If a combined decision rule is introduced later, validate that rule on data not used to choose it. Keep raw survey artifacts, normalized coordinates and selection code with the analysis record.

## Limitations

A high score can reflect correlations in the training sample rather than youth. Missing or blended photometry, survey rendering differences, extinction, cadence and training-set overlap may change behavior. Agreement among architectures does not guarantee independent evidence. The software should not be described as scientifically validated until the missing evaluation record is completed.
