# Native detection on the classification and corpus stack

This source-only candidate reconciles preserved native detection commit
`b85d53992ed5b6aeb35fa80f38c6aac9356c0f40` (tree
`626d2a23fe544f9c578c7dc898bf7fddae433d6f`) onto exact corpus PR28 head
`b98e5e74fae6476294a6b979d73dd86c28c26253` (tree
`520359ebb35bac1351f677baa0e5f4133c307607`). Its direct parent is classification
PR27 head `3cd0dc76e46e6d7798ae34fc9e3f35ca31dfbe6e` (tree
`965e7d93110e3d503f78ec3e18f8afb2869ef4ba`), which retains saved searches
`cdb8e241b002c5beef464df1bec36f10efb7023e`.

The new branch is `feature/native-detection-stack-20261008`. Main remains frozen
at `2fc4a46f12d73a0fa467d5482f68edb83d6df6af`. The preserved b85 worktree,
source, accepted and failed artifacts are immutable. This candidate does not
mutate either parent feature ref. A normal upstream feature merge preserves
these commit dependencies. Historical plans remain historical; final source,
qualification, review and any publication identities belong to separate receipts.

## Review before reconciliation

Independent design review admitted additive reconciliation after inspecting the
actual b98 exporter and b85 consumer. The canonical detection manifest, geometry,
COCO indexing, vocabulary and stored ZIP schema are unchanged. Keep newer corpus
validation, human review rules, bounded selections, all four export controls,
saved searches, pinned consumers and QA ownership.

Only README and Workbench HTML conflicted. The resolution adds the original
detection documentation, panel and script to the newer files. Removing the HTML
insertions reconstructs exact b98. Shared release, classification/corpus exporter,
native text importer, Workbench browser controller and all authored base fixtures
remain byte-exact b98. Detection adapter and controller remain byte-exact b85;
the existing narrow Workbench initial annotation composition remains additive.

## Combined checks

`tests/test_native_detection_stack.py` exercises the actual owners and exporter:
three explicitly reviewed authored corpus documents, fixed selection and dynamic
search, an unrelated frozen classification release, and a one-image native export
whose retained origin group connects to the selected corpus family. Admission
preserves targets and saved identities, revokes the old family proof, and permits
explicit repreview with the imported train boundary and exact raw corpus bytes.
A conflicting existing validation member rejects admission without any database
change and preserves the prior preview. These are compatibility fixtures, not
scientific or training-quality data.

The extended real Chromium gate repeats that association through the ordinary
native ZIP form, retaining a dirty corpus note and exact selection. It checks
server and rendered stale-proof rejection, explicit repreview, exact corpus bytes,
the unselected imported family member and immutable earlier native release.
Existing cancellation, duplicate, delayed-refresh, lost-response lookup,
review/export, reload/back and narrow-layout checks remain. Public classification,
corpus and saved-search gates are retained in the full workflow aggregate.

## Bounds and evidence

Detection accepts 1–100 canonical image-detection records, at most 8 MiB stored
ZIP and 16 MiB expanded content, 3 MiB decoded signed row, 16 MiB combined signed
tokens and 40 million pixels per image. It validates normalized RGB PNG bytes,
measured geometry and hashes, exact annotations and associations before admission.
Consumed exported PNGs are the available input; earlier originals and omitted
upstream bridges remain unavailable. New records are draft with unknown rights;
validation never grants review. Initial annotations use existing oriented
pixel-edge xywh semantics and Dataset-owned atomic acquisition. Exported splits
and retained connected family links cannot cross local splits.

Qualification uses isolated pinned local consumer software and actual registered
offline consumers. It never downloads models or invokes a simulation. Reuse only
the previously accepted Rheon `fee7b4a139574f87b259796b1ba8698a41d31ac1`
pilot; the newer producer head is not automatically accepted. This imports data;
it does not qualify a training model or scientific dataset. UI remains provisional.

All new logs, accepted/failed attempt receipts, source bundle, source hashes,
artifact manifest and final review stay under the separate
`/workspace/native-detection-stack-qualification` evidence root. Final aggregate
and independent source review must pass against the frozen candidate before any
ordinary new stacked draft publication; no merge, deploy, force push or protected
branch update is performed by this candidate.
