# Publication checklist

The release candidate is not ready for public distribution until the items below are complete.

## Maintainer decisions still required

- The NGYSO I paper authors and accepted-paper reference are documented in [Scientific context and citation](PAPER.md) and `CITATION.bib`; finalize software-specific contributor credits separately.
- Select and approve the software license; no open-source permission is implied by this release candidate.
- Confirm model ownership and redistribution terms for all 48 checkpoints. Code and model licenses may differ.
- Repository: https://github.com/martongabor/DLYSO. Confirm public distribution readiness and add the paper DOI and final journal details when assigned.
- Attribute scientific performance to the NGYSO I evaluation; complete the release-specific reproducibility record described in the model card.

The paper reference is supplied in `CITATION.bib`. Add `LICENSE` after the license decision and software-specific `CITATION.cff` metadata once contributor credits are finalized. Do not invent an unassigned DOI.

## Software checks

- [x] Offline regression and desktop tests pass.
- [x] Lint passes.
- [x] All 48 checkpoints match the manifest and pass the CPU smoke check.
- [x] Source archive and wheel contain documentation, examples and helper code.
- [x] Source archive excludes private data, credentials and unrelated artifacts.
- [x] Desktop screenshots have been inspected at normal and minimum sizes.
- [x] Single-source archive smoke run is recorded, including skipped services.
- [x] Supported OS/interpreter claims match platforms actually tested.
- [x] Dependency constraints and verification notes are updated.
- [ ] License, authorship and model redistribution terms are finalized.

See the [verification record](VERIFICATION.md) for dates and results. CI runs offline checks; it does not establish live archive availability or scientific performance.
