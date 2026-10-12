# Independent review: audio execution and static-mesh inspection

## Admission review

Reviewed the `continue` admission at
`d4a5b19665018f49f55769de2706633c0600d373`, canonical plan blob
`d7c0b894219da0d229eee960b9a11616805276a5`, against verified main
`ee81555586ef96c56b78dde1858f3c5f689b27c1`. The
[admission](audio-mesh-admission-20261012.md) names root as serial integration
owner and separates audio, mesh, shared routes/presentation and independent
review write sets. Adopted standards remain
`dcc56f26e884ade260770beceba2501d3746200d`; Core, Router, Verification and its
oracle/GUI details, Implementation, Commit, Documentation, Persistence and the
concurrent-plan profile were consulted. No Engine certification is claimed.

**Decision:** admitted scopes are suitable for implementation. This decision
does not accept source, screenshots, numerical results or feature CI. A11 and
A12 remain pending those observations. No main merge or deployment is admitted.

## Review boundaries

Audio reuses schema 3 and the existing graph/run supervisor. The declared one
labelled interval per recording avoids introducing a second example identity
model. Exact channel, half-open source frames, annotation/source revisions and
original WAV custody remain authoritative. Split allocation must precede
feature extraction and retain all known protected-family bridges. Whole
decoded-PCM exposure identity must include sample rate and channel count and
remain independent of interval selection; changing an interval or RIFF metadata
must not make previously exposed audio appear fresh.

The shared family-reader extraction is compatible only when new text probes and
private worker staging hash and copy the extracted module. Existing completed
text results must continue to validate against their own frozen source/runtime
identity, not newly computed source hashes. Old graph digests, model meanings
and artifacts remain unchanged. New validation tokens should become stale when
the current executable definition changes. Retained-result reads and a new real
text run exercise different compatibility claims and both need evidence.

The fixed audio features and train-only scaler need an independent small numeric
oracle, including silence and known channel/frame signals. Real classification
must remain separate from transcript/ASR claims. Cancellation must prove worker
cessation; restart must not replay a run. Existing lost-ack, retry, test exposure,
artifact integrity and correction behavior apply to the new closed recipe.

Mesh remains the existing bounded ASCII static-mesh profile. Its original byte
and native-value ownership must survive screen transforms. The new validator's
`selected_records_only` result accurately limits canonical release family
evidence; omitted ancestors cannot be certified by this format. No training,
physics, general PLY compatibility, whole M5 completion or external reader
conformance follows from local parsing and selected-row consistency.

The inspected candidate heads were bounded acquisition
`dd7661d8bff789a5de3b88addb4ea88370466ea7`, native mesh
`b4f89fa04dd97622db9a21c3d33188e5086efa51` and native point cloud
`97b8f5ad6cbe6cac218dac48c6b3d6f8036f91a3`. The acquisition stack changes 392
files relative to the common baseline; the native mesh consumer imports
candidate-only sequence/point-cloud consumers and release helpers. No candidate
implementation was adopted during review. Its documented ASCII float32
double-rounding counterexamples inform precision checks, while this increment
keeps the accepted parser and uses authored native-bit expectations.

Sequence v1 remains unchanged: whole nine-frame trajectories, declared native
field types and MAC shapes, original units and last-accepted-interval pressure
semantics. Its regression checks do not authorize an expanded simulation path.

## Shared presentation and route review

Reviewed root's audio selector commit
`2faae82445f55483ee408ba519c1cb304a84c63c` and mesh integration commit
`2344b819c21a92bb32a1dfbc386b030888400212` independently. No blocking finding
within these narrow changes. An exact before/after comparison proves the audio
HTML adds only one `audio_classification_v1` option and preserves every prior
byte; existing recipe/context behavior is unchanged by that commit.

Every core release-result clearing site now emits `tuldok:release-cleared`.
Publication remains after the existing request epoch and exact release-body
checks, and after constructing the current download link. An obsolete response
cannot publish the validation handle. Only canonical exports emit that handle;
image/text-specific exports retain their existing behavior. The GET adapter
first uses the release owner's bounded identity/location check, then delegates
validation; it adds no mutation or alternative archive authority.

Independently ran `node tests/test_workbench_controller.cjs` against exact
`static/workbench.js` blob `e5219ae0c82206181cd564dc111aef5870904216`: passed.
The test observes stale preview/export suppression, repeated request fencing,
current publication identity and clearing after selection changes. Source
review also confirms the other controller changes supply the newly used DOM
event primitives rather than removing assertions. Root reports all ten affected
controller suites passed; the reviewer reran the directly relevant one.

This accepts only the shared wiring. At this point `mesh_release.py` and its
UI consumer were still implementation candidates. Typed validation errors,
late-response suppression, preservation of an existing download after validation
failure, rendered controls and complete browser behavior remain feature gates.

## First mesh visual checkpoint and retained-result procedure

Viewed both original JPEGs from the mesh owner's
`build/qa/workspace-mesh/run-HdbmHD`: desktop 1400×950 and narrow 390×844.
The spatial drawing and seven buttons are legible; narrow buttons remain in two
columns with a full-width reset. The diagram and explanatory text remain inside
their card without visible horizontal clipping. First-8-of-8 sampling and
source frame/unit captions are explicit. No blocking visual finding in this
early checkpoint. The receipt accurately identifies dirty source based on
`2344b819c21a92bb32a1dfbc386b030888400212` and `native_zoom: false`; this is not
clean-source or native-200% qualification. Final embedded `/workspaces` Data,
validation-result/download and native-zoom evidence remain pending.

Original screenshot SHA-256 values:

- `mesh-desktop.jpg`: `827d476c9b153d481f4312cb5cfa3228c08c108c79300d20278978722c9251d7`.
- `mesh-narrow.jpg`: `ea92acc1e076bc1baeb01042d095f7a1e73ed22fcd4387fdb3c3110dabe4ec31`.

Read root's `/tmp/tuldok-audio-mesh-retained-20261012/check.py` and
`before.json` without executing the script or opening either catalog. The
procedure observes public completed runs and both split prediction references,
exact graph/run/exposure rows, and every managed file's length/hash except
volatile `*.lock` files. It blocks `subprocess.Popen`, requires no supervisor
thread and compares rows/files before and after observation. Its baseline
contains authored text run `1cfdf8fb3fe54ff599f0c6891a53af07` (17 files, four
exposure rows) and image run `36a82a2ff267465d90c4ad69fa7a9496` (51 files, three
exposure rows). This procedure can decide retained-result compatibility when
root compares candidate output byte-for-byte with that baseline; that comparison
was still pending at this review.

## Audio release and graph checkpoint

Reviewed exact source `1959775933030a3639ad504143207d9d8d786f1d` from an
immutable temporary archive, independent of subsequent worker edits. No blocking
finding in the bounded release/graph checkpoint. The target binds one exact
reviewed interval/channel to original WAV bytes; decoded whole-record identity
includes rate and channels and does not depend on interval coordinates. Family
allocation remains release-owned. The extracted reader preserves the previous
text validation algorithm and diagnostics, and new text definition identities
include the module copied into private worker staging. The lazy custody import
does not change the WAV admission transaction or rollback paths.

Independently ran five audio release/graph tests in 2.733 seconds and fourteen
text reader/trainer/run tests in 12.966 seconds, all passing without skips,
against this source with the configured local PostgreSQL and CPU interpreter.
Text evidence includes a new actual CPU result, restart, exposure/correction,
deleted/unselected family bridges and inherited-thread limits. Test catalogs
were independently disposable; retained catalogs were not opened by review.

Independently compared root's retained `before.json` and
`audio-checkpoint.json`: exact equality of all 133,437 bytes. These cover both
old public runs, validation/test prediction references, raw graph/run/exposure
rows and 68 managed files. Reviewed the clean source-bound desktop Pipeline and
narrow Data images in `docs/images/workspaces-audio-runs-checkpoint/`; readable
controls and no visible horizontal clipping, with explicit unavailable trainer.
The receipt binds clean source 1959775, four actual-browser checks and no training
or quality claim. This accepts the first checkpoint, not real audio execution.

## First mesh source review and required repairs

Reviewed exact `44664439124bf2d738ce823e3e4ed6d936709d8e` from an immutable
temporary archive. Independently ran all four mesh-release PostgreSQL tests in
1.104 seconds and the mesh controller suite: passed. Authored geometry provides
explicit asymmetric coordinates, ordered faces, mixed property types and
positive/negative float32 midpoint-neighbor bit expectations. The reader keeps
the original parser and source bytes, reports selected-row family scope, and
the UI's generation/abort ownership leaves the existing download outside its
mutation boundary. Two demonstrated consumer incompatibilities block acceptance:

1. **P2 — empty human note rejected.** The existing mesh annotation owner admits
   `{"note":""}` with an explicit human review decision. The new validator's
   additional `note.strip()` requirement rejects this valid canonical export.
   Root independently found the same issue. Remove the extra policy and prove
   actual empty-note review/freeze/validation while preserving draft rejection.
2. **P2 — Unicode code-point bounds interpreted as UTF-16 units.** Actual
   import, human review, freeze and server validation succeed for an authored
   sidecar whose frame is 61 `😀` characters, within the 120-code-point contract.
   The exact browser decoder rejects that valid report because JavaScript
   `.length` returns 122. The same helper affects name, rights and provenance.
   Count Unicode code points consistently and test valid and over-cap boundaries.
   The reviewer reproduced this through a separate real PostgreSQL catalog and
   the exact `decodeMeshReleaseReport` function, without changing application
   source. Root sent the scoped repair to the mesh owner.

The passing original tests did not cover these two paths. Required repairs and
their exact source/regression evidence remain pending; no mesh feature
acceptance or waiver is recorded.

## Pending qualification

- Review final candidate SHAs, the two mesh repairs and final original screenshots.
- Observe the complete audio Data → edited Pipeline → real Runs → correction
  path, plus independent numeric/PCM and retained image/text evidence.
- Observe mesh import → spatial inspection → review → freeze → downloaded
  archive validation, including independent coordinate/topology expectations.
- Inspect keyboard/repeated/loading/error/stale/empty behavior and responsive
  evidence; verify source-bound screenshots and honest capability text.
- Review serial integration and applicable automatic feature CI to terminal
  outcomes. Failed evidence remains visible until a scoped repair qualifies.

Review branch `review/workspace-audio-mesh-20261012` and worktree
`/workspace/Tuldok-next-review-20261012` are retained for independent evidence
and later root integration. The reviewer owns only this report and its named
evidence; application source and the canonical plan are read-only.
