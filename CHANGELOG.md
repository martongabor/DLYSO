# Changelog

## 1.1.0rc1 — release candidate

- Expand the example catalogue to 13 sources, adding 11 with downloaded public ZTF light curves and verified DTDM rendering; record per-band counts and archive IDs.

- Add automatic model and CSFD installation with checksum verification and user-data discovery.
- Fix relative documentation links in the desktop and add Back navigation.

- Show one progress bar per modality, combining acquisition, plotting and both classifier stages.
- Document GitHub installation and add source-package exclusions and a Git installation check in CI.

- Simplify page headings and documentation wording; update instructions for incremental results and CLI activity logs.

- Schedule classification per representation as soon as it is ready; isolate channel failures, serialize inference, and publish incremental results without stale predictions.

- Replace the Tk form with a native Qt workspace: catalogue preview, channel cards, activity stages, searchable results, per-source images and an integrated field guide.
- Distinguish missing predictions from negative votes, including when viewing and exporting legacy tables.
- Record rejected coordinate rows and reject non-finite/out-of-range coordinates.
- Use anonymous, bounded HTTPS requests for public ZTF light curves; remove login fields, credential options and authentication plumbing.
- Treat AllWISE image-quality rejections as missing evidence, keeping other channels running; recognize legacy median-test markers and allow explicit re-querying.
- Retry malformed VizieR SED responses using equivalent query encodings; validate photometry columns and record per-target errors.
- Report ZTF target progress and preserve archive error messages in the activity log and failure markers.
- Retry failed artifacts; use atomic download writes and surface failed target counts.
- Drain CLI download output without pipe deadlocks; cancel desktop process trees and persist logs/stage state.
- Record input, software and model hashes; reject incompatible project reuse.
- Add installation diagnostics, model checksums, packaging, release assembly and regression tests.
- Rewrite user, CLI, output, model and developer documentation; ship an offline HTML reference.

No new scientific accuracy claim, retraining or threshold optimization is included.
