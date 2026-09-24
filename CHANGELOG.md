# Changelog

## 1.1.0rc1 — release candidate

- Expand the example catalogue to 11 YSOs and 9 named, SIMBAD-verified non-YSO comparison objects, with reference labels separate from predictions.
- Show setup downloads on one terminal line, and report complete CSV validation counts in Project.
- Add per-channel Classification labels to Results and CSV exports using six of twelve votes; incomplete evaluations remain unlabeled.

- Correct the SEDr SqueezeNet vote threshold from 0.757 to the author-confirmed 0.577. Recombine saved predictions to update SEDr vote totals; inference scores are unchanged.

- Correct AllWISE custom model vote thresholds to SmallResNet 0.500 and RCA 0.580, as confirmed by the authors and manuscript. Recombine existing predictions to update votes; model scores are unchanged.

- Convert ensemble logits to float32 before softmax, keeping AMP acceleration while fixing bfloat16-to-NumPy export on supported CUDA GPUs.

- Update the sidebar subtitle and replace synthetic documentation screenshots with current widgets and real public ZTF classification results.

- Keep GUI text, inputs, selections and documentation readable under macOS Dark Mode with an explicit application palette.

- Replace the placeholder examples with 11 named sources with downloaded public ZTF light curves and verified DTDM rendering; record per-band counts and archive IDs.

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
