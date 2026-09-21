# Publication checklist

The release candidate is not ready for public distribution until the items below are complete.

## Maintainer decisions still required

- Confirm the author name, affiliation and preferred citation.
- Select and approve the software license; no open-source permission is implied by this release candidate.
- Confirm model ownership and redistribution terms for all 48 checkpoints. Code and model licenses may differ.
- Provide the public repository URL and release/archive location. Do not invent a DOI.
- Complete the model-card evidence before publishing accuracy or scientific selection claims.

A real `LICENSE` and `CITATION.cff` should be added after those decisions. Do not publish placeholder authors, invented metrics or an unassigned DOI.

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
