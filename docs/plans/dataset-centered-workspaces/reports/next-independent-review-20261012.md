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
`build/qa/workspace-mesh/run-HdbmHD`: desktop 1400×807 and narrow 390×844.
The receipt's 1400×950 desktop size describes the requested window, while the
published original image has 807 content pixels in height.
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
mutation boundary. At that head, two demonstrated consumer incompatibilities
blocked acceptance:

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

The passing original tests did not cover these two paths. Both were repaired at
`8320c9066858cef73d493b9a97b7fcfa39bc655d` and independently accepted. The original
actual-producer 61-emoji report passes the repaired exact browser decoder. All
six PostgreSQL reader tests passed in 1.515 seconds and the controller suite
passed against an immutable archive of 8320c90. New evidence covers actual empty
human-note export, supplementary Unicode at all declared caps, over-cap fields
and lone-surrogate refusal. No demonstrated source blocker remains. These
repairs do not waive final browser, screenshot, integration or CI gates.

## Real audio execution and verified-byte custody

Reviewed the actual CPU adapter and run integration at
`61a9f67671fcd2efa7d872a5710e746cf9b29e29` from an immutable source archive.
All twelve focused audio tests passed independently in 76.350 seconds without
skips. They exercise actual child cancellation/drain and fresh retry, abrupt
supervisor death and interrupted reopen, binary and three-class training,
nonconvergence refusal, train-only scaling, exact interval/channel selection,
source-family guards and unavailable-runtime refusal. The numeric oracles use
analytic PCM cases and a scalar standard-library DFT/probability implementation;
they include silence, DC, Nyquist, quarter-band boundaries and an odd 129-frame
impulse. This is bounded audio classification, with no ASR or acquired-audio
quality claim.

That passing suite did not cover one independently demonstrated **P2 custody
defect**. After the reader verified captured ZIP bytes, training reopened the
release path after its runtime probe. A probe-boundary replacement with a valid
ZIP containing zero-valued WAVs made the actual trainer publish an artifact
manifest under the original frozen release hash while its saved RMS feature
mean was zero. The original and replacement SHA-256 values were respectively
`113287da9de23d15b56cc5cdcacf74371f60826f8dd3c64bc323d67d32527d89`
and `0d56974daca150c674b4b91f15789528597a6b6ebde8898462408f5e61c38ff5`.
Review used a separate disposable PostgreSQL catalog and retained no user data.

Repair `5db224059162e2600bb4f05d754de167f4d752f3` is independently accepted.
The private reader returns its validated manifest and owned immutable byte
capture; training reads `BytesIO` over that same capture. Public
`inspect_release` still returns only the manifest. No second path read or
fallback can select different samples. All thirteen focused tests passed from
an immutable archive in 55.721 seconds with no skips. A separate reviewer probe
atomically replaced the path after verification and computed an independent
scalar RMS oracle from the original training intervals: expected mean
`0.2006054927052682`, saved mean `0.20060549270526823`. The replacement contained
zero PCM; the published model retained the original release identity and used
the original samples. Local evidence is
`/tmp/tuldok-audio-owned-capture-independent-5db2240.json`, with rerunnable probe
`/tmp/tuldok-audio-owned-capture-independent.py`. A byte-identical durable copy
of the result is now in the
[audio gallery](../../../images/workspaces-audio-runs/independent-owned-capture.json).
No demonstrated audio source blocker remains after this repair.

Independently compared root's `before.json` and `audio-final.json` in
`/tmp/tuldok-audio-mesh-retained-20261012`: all 133,437 bytes match. This is the
retained image/text proof at clean 61a9f67, including both public completed runs,
both prediction sets, raw rows and 68 managed files. The reviewer compared
evidence files without reopening retained catalogs. The combined-candidate
comparison is recorded below.

## Final mesh source and visual qualification

Accepted final mesh source and visual evidence published at
`dfe7a3e0a1405f5739153382902467c115699cd4`. Its clean browser receipt binds
`0685d91afd195e64c5f4b1793f0a28be3d470d1d`; runtime changes since repaired
8320c90 are limited to accurate explanatory HTML about draft import, explicit
human review, original geometry and source declarations. Later commit
`1ed743316afd7a4d5447a7c4a927561bc5fc501f` supplies `CustomEvent` and
`dispatchEvent` to the existing preference-controller VM without removing or
weakening assertions. The reviewer independently reran preference and mesh
controller suites successfully.

Viewed all four final original JPEGs in the
[mesh gallery](../../../images/workspaces-mesh-20261012/README.md). Embedded
Data at 1440×1000 and 390×844 has readable spatial controls without horizontal
clipping. The 1400×807 release view shows a usable current download beside
bounded integrity validation and its selected-record family limit. The genuine
native-200% 1400×807 image has readable controls and visible keyboard focus.
All six gallery file lengths/hashes match the manifest; all four final files
are byte-identical to `build/qa/workspace-mesh/run-PgDfuJ` originals. The receipt
records clean source, authored real PLY bytes and native zoom, without physics
or general-reader claims.

Inspected the final real-browser harness: it uses embedded `/workspaces` Data,
checks actual raw-asset byte equality, holds real inspection/validation replies,
checks repeat-submit suppression and stale-response clearing, and preserves a
usable canonical download when the narrow mesh reader refuses a mixed release.
Keyboard review submits the real form; native zoom uses browser shortcuts and
observes both device-pixel ratio and halved content width. This supports the
bounded mesh flow and does not establish general PLY conformance or completion
of all 3D work.

## Final audio visual qualification

Accepted clean source-bound audio gallery publication
`cf684f7de2be7e828cade7c11ad3249b65413502`. Its receipt binds runtime source
`292ba880b8bdcb80a469e5d370e29e5f006929a9`, thirteen actual-browser checks
and fifteen original JPEG85 captures. The only runtime change after the
accepted custody repair clarifies prediction copy: `Source channel 1 (index 0)`
and `Source channel 2 (index 1)` agree with the existing Data editor while
preserving the zero-based wire coordinate. Source review confirms this is
renderer wording only; the service already checks integer channel bounds.

Independently viewed all fifteen originals in the
[final audio gallery](../../../images/workspaces-audio-runs/README.md) and
verified all eighteen manifest hashes. The saved interval controls and frozen
prediction references remain legible at 390 pixels. Desktop, 1024-pixel, narrow
and genuine native-200% views have no visible horizontal clipping. The native
receipt observes device ratio 1 → 2 and CSS width 1440 → 720. Running progress
states unknown duration and cancellation only after worker cessation. Completed
results keep test artifacts locked; correction shows frozen annotation r2 and
current r3 with unchanged old results. The small-run quality limitation remains
visible. These are actual authored PCM runs, without ASR or model-quality claims.

Inspected the final browser harness through its real HTTP and UI workflow:
loading/error retry, delayed-response navigation, disconnected graph refusal,
stale validation before admission, lost committed response and explicit receipt
reconciliation, actual CPU completion, later-intent correction fencing, a new
reviewed release, durable test exposure and application restart. Original
release bytes and frozen predictions are compared across correction/restart.
Gallery evidence distinguishes HTTP fixture setup from subsequent browser
actions; it does not claim that fixture import was manually performed in Data.

## Serial integration review

Independently checked merge
`9d9e18eb5038e3fce02c82f090ed885c0e68fda2`: its conflicted workbench HTML is
byte-for-byte the first parent's audio HTML with only the two admitted mesh
changes applied (stylesheet and explanatory paragraph). No resolution drift
was found. Candidate `148e7af25477d71359b7b205dc07eb715fa1f6d9` contains
byte-identical accepted audio runtime files from 5db2240 and mesh runtime files,
routes and workbench publication logic from dfe7a3e. The reviewer independently
compared these files against both owner heads, beyond the HTML composition.

Root produced `combined-final.json` on exact clean 148e7af. The reviewer
independently compared it with the retained baseline: exact equality of all
133,437 bytes, SHA-256
`c2894f78259f53c65fbd96b91ac83079f67206fca377b975cbbcc839ff1ce734`.
This includes the custody repair and preference VM adapter. The later audio
channel-copy change has no backend or stored-result effect. Complete combined
execution and terminal hosted CI remain separate gates.

Hosted mesh lifecycle run `38265471446` on dfe7a3e subsequently exposed a missing
`CustomEvent` primitive in the saved-selection intent test VM, after 543 Python
tests passed in 253.948 seconds. Earlier controller globs did not include that differently named test;
the successful subsets do not establish full controller qualification. No
application fallback or assertion weakening is justified by this failure.

Repair `4266a76b7a86f89e707ae166d535bce2768c5a32` is independently accepted:
it adds only the native `CustomEvent` binding and `window.dispatchEvent` stub to
the VM. All eight existing scenarios pass when independently executed at the
exact repair head. No assertions, scenarios or application files changed.
Root separately reports all twenty-two controller/intent suites passed in one
completed batch. Hosted CI must still run to completion on the repaired head.

Root's full Python qualification on exact 148e7af completed 556 tests in 503.794
seconds, with one existing restore test skipped because the app role lacks
`CREATEDB`. Root then ran that exact skipped case using the isolated local test
administrator: one test passed in 3.168 seconds. This reports the limited-role
skip and separate verification explicitly; it does not claim a zero-skip suite
or broaden application database privileges. These are root-run observations,
separate from the focused tests independently executed above.

## Pending qualification

- Bind final serial integration, including presentation-only channel copy and
  accepted test VM repair, to its exact source and local qualification evidence.
- Review serial integration and applicable automatic feature CI to terminal
  outcomes. Failed evidence remains visible until a scoped repair qualifies.

Review branch `review/workspace-audio-mesh-20261012` and worktree
`/workspace/Tuldok-next-review-20261012` are retained for independent evidence
and later root integration. The reviewer owns only this report and its named
evidence; application source and the canonical plan are read-only.
