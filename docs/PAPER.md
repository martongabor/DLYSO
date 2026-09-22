# Scientific context and citation

DLYSO (deep learning young stellar object identification) is the companion software to **NGYSO I**, *The NEMESIS general YSO catalogue. I. Supervised classification with deep learning methods* by Marton et al. (2026), accepted for publication in *Astronomy & Astrophysics*.

Developed within the NEMESIS project, DLYSO applies image-based deep learning to the identification of young stellar objects. It retrieves archival photometry, AllWISE infrared images and ZTF light curves, constructs four complementary input representations, and evaluates them with standard and custom convolutional neural networks. The desktop and command-line interfaces bring this workflow to user-supplied source catalogues, preserving individual model scores, per-channel votes and data-coverage information.

## Relation to NGYSO I

The paper describes the training samples, image representations, network architectures, threshold selection and scientific evaluation underlying the NGYSO classification approach. It uses spectral energy distribution (SED) images, SED images with a dust-context background, AllWISE image cutouts and ZTF time–magnitude-difference (DTDM) maps. Each representation is evaluated by an ensemble of ten standard CNN architectures and two custom models, SmallResNet and ResConvAttnClassifier.

The final NGYSO catalogue in the paper contains 274,408 unique candidates selected using the ordinary-SED ensemble. The paper's selection requires at least six positive votes from twelve SED models. DLYSO exposes the scores and votes for each available channel; agreement across channels is not presented as a calibrated joint probability. Applying the software to a new sample does not automatically reproduce the paper's catalogue selection or its evaluation sample.

The supplied manuscript calls the software **YSODL** and explicitly links to `github.com/martongabor/DLYSO`. This repository, application and Python package use **DLYSO** (`dlyso-pipeline`).

## How to cite

When using DLYSO in research, cite NGYSO I for the method and report the software version or Git commit used. The current paper reference is:

Marton, G., Madarász, M., Roquette, J., Audard, M., Gezer, I., Hernandez, D., & Dionatos, O. (2026). **The NEMESIS general YSO catalogue. I. Supervised classification with deep learning methods.** *Astronomy & Astrophysics*, accepted for publication.

The article is accepted but not yet published. DOI, volume and article number will be added when assigned. The year above follows the 2026 manuscript; update the citation to the final journal record when available.

```bibtex
@article{Marton2026NGYSOI,
  author = {Marton, G. and Madar{\'a}sz, M. and Roquette, J. and
            Audard, M. and Gezer, I. and Hernandez, D. and Dionatos, O.},
  title = {The {NEMESIS} general {YSO} catalogue. {I}. Supervised
           classification with deep learning methods},
  journal = {Astronomy \& Astrophysics},
  year = {2026},
  note = {Accepted for publication}
}

```

The same entry is available in [`CITATION.bib`](https://github.com/martongabor/DLYSO/blob/main/CITATION.bib). Record the [software repository](https://github.com/martongabor/DLYSO), release or commit, model manifest and selected channels alongside the paper citation to identify the analysis configuration.

## Scientific performance

The paper reports 96.36% recovery of labelled YSOs and a 0.43% false-positive rate among labelled non-YSOs for the ordinary-SED ensemble on its test set. These are paper-specific evaluation results, not a measurement of contamination in every catalogue processed by DLYSO. The present software checks establish installation and inference behavior; they do not independently reproduce that scientific evaluation. See the [model card](MODEL_CARD.md) for implementation details and limitations.
