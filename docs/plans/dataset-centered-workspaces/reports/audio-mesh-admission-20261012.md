# Audio execution and static-mesh admission — 2026-10-12

The user requested continued Tuldok development with parallel agents after
approving PR34/35's merges. This admits `continue` against the Active/partial
`docs/plans/dataset-centered-workspaces/plan.md`. Main was rechecked before
implementation at **ee81555586ef96c56b78dde1858f3c5f689b27c1**, with no newer user
commits. Its tree is the previously qualified PR35 head d3b1a31: 537 Python
tests and all 102 hosted lifecycle steps passed without skips, plus focused UI
CI. New feature acceptance is separate. Adopted standards remain dcc56f26;
Engine MCP is unavailable and no Engine certification is claimed.

## Ownership, revision and isolation

Root owns the canonical plan and serial integration. Admission uses the Git
blob OID of this plan at the admission commit, sent to each worker before edits.
Compare that OID and affected shared authority before the first shared write
and before integration. A changed revision requires root's explicit semantic
reconciliation; it does not authorize silent rebase or overwrite. Both proposals
have prerequisite `none` beyond this admitted baseline; neither depends on the
other feature. Complete published branches retain their history.

| Owner | Branch / worktree | Exact candidate write set |
| --- | --- | --- |
| audio_runs_next | `feature/workspace-audio-runs-20261012`, `/workspace/Tuldok-audio-runs-20261012` | New `audio_classification_export.py`, `audio_training.py`, `frozen_classification.py`; audio-only hooks in `dataset_releases.py`, `pipeline.py`, `runs.py`, `static/workspace-real.js`, `static/workspace-service.js`; narrow `audio_assets.py` lazy custody import and `text_training.py` delegation to the shared family reader; `tests/test_audio_training.py`, `tests/browser_workspace_audio_run.cjs`, audio-specific fixtures, contract/report/gallery |
| mesh_next | `feature/workspace-mesh-inspection-20261012`, `/workspace/Tuldok-mesh-next-20261012` | `static/meshes.js`, new `static/meshes.css`, `mesh_release.py`, `tests/test_mesh_release.py`, affected `tests/test_meshes_controller.cjs`, new `tests/browser_workspace_mesh.cjs`, mesh-specific fixtures, `docs/contracts/static-mesh.md`, new mesh validation contract/report/gallery |
| next_review | `review/workspace-audio-mesh-20261012`, `/workspace/Tuldok-next-review-20261012` | `reports/next-independent-review-20261012.md` and report-specific evidence only; application read-only |
| root | `integration/workspace-audio-mesh-20261012`, `/workspace/Tuldok-audio-mesh-20261012` | Plan/ledger/issues; narrow `app.py`, `static/workbench.html`, `static/workbench.js` integration; README, CI registration, integration tests/report and shared evidence |

Audio does not edit mesh files; mesh does not edit release/graph/run owners.
Root supplies shared route/HTML/event commits sequentially to the relevant
feature branch. Adjacent edits require owner agreement before mutation. Each
feature gets a separate draft PR targeting main and its applicable checks;
root may compose a separate integration candidate for cross-feature regression.
No new main merge, deploy, user-computer execution, private-data migration,
paid service or model download is admitted. PR32/33 remain unchanged.

New worktrees remain owned proposals during implementation/review. At handoff,
record exact retained heads and purpose; retain feature branches/worktrees for
draft review and the integration demo until later approval or explicit closure.
Do not clean older worktrees, running services or fixture catalogs belonging to
other tasks. No shared history rewrite or force push.

## Audio checkpoints and contract

1. Runnable release/graph checkpoint: authored PCM data imports through existing
   Data, human review freezes `audio_classification_v1`, and an editable named
   audio graph shows real validation. Until the trainer exists, execution is
   explicitly unavailable. Capture Data and Pipeline at desktop/narrow widths.
2. Real execution checkpoint: use fixed eight features (mean, RMS, adjacent
   zero-crossing fraction, normalized spectral centroid, four equal Nyquist-band
   power fractions) of selected PCM16 samples divided by 32768. NumPy rFFT uses
   a rectangular window; silence spectral features are zero. There is no
   resampling, downmixing, inferred transcript or learned feature extractor.
   Fit StandardScaler only on train, then scikit-learn 1.7.2 LogisticRegression
   with lbfgs, max_iter 200, tol 1e-6, editable C 0.01–100 (default 1). Treat
   nonconvergence as failure. Publish closed JSON coefficients/scaler plus real
   metrics and exact per-record frame/channel predictions, never pickle.
3. Qualified workflow: correction/new release, immutable earlier results,
   explicit test exposure, cancellation with confirmed child cessation,
   interrupted restart and intentional new attempts, lost-ack reconciliation,
   tamper refusal, real browser screenshots and independent numeric/PCM review.

Bounds: 6–256 recordings, 2–8 classes with every class in train/validation/test;
exactly one reviewed nonempty class-labelled interval per recording, 128–65,536
frames and at most 10 seconds per interval, at most 4,194,304 analyzed frames and
40 MiB aggregate original WAV bytes. Keep original WAVs and exact source,
annotation, channel and half-open frame references. Allocate whole protected
record families, including unselected/deleted bridges, before training; selected
intervals are not independent recordings. Source/decoded-PCM exposure must
survive interval changes and reimports. Tiny authored signals prove operation,
not useful accuracy or semantic independence. ASR remains unavailable.

The narrow `audio_assets.py` lazy import leaves custody/rollback unchanged while
allowing the existing parser in the isolated worker. Shared complete-family
validation moves out of the text adapter only to prevent a second divergent
reader. Preserve text validation meaning and retained image/text graph/run
digests, artifacts and restart behavior; source-bound new recipe identities
must include their actual copied dependencies. No schema or runtime dependency
change is admitted.

## Mesh checkpoints and contract

1. First runnable view: retain existing XY/XZ/YZ projections and add bounded
   orthographic spatial inspection with yaw/pitch, zoom and reset buttons.
   All controls work without dragging. Show original axes/units/frame, whole
   bounds and first-512-triangle sampling; screen transforms never change bytes.
2. Frozen validation: stdlib `mesh_release.py` validates mesh-only canonical_v1
   archives through a CLI and a root-owned local GET adapter. An explicit button
   beside the existing successful release download renders its bounded report.
   Release-published/cleared presentation events fence late responses; validation
   never mutates/reviews records or invalidates a usable download.
3. Qualify import → inspect → human review → freeze → download → validate with
   authored asymmetric mixed-dtype fixtures, independent known coordinate/bit
   and topology expectations, keyboard/repeated actions, loading/error/stale
   states, desktop/narrow screenshots and existing sequence regressions.

Validate bounded archive paths/entries/JSON, hashes and file associations,
reparsed native geometry, manifest/JSONL agreement, review snapshots, units,
frame and selected-row family consistency. Canonical_v1 does not freeze every
omitted ancestor: report `selected_records_only`, never full independence or
complete leakage proof. Reject mixed/unsupported exports explicitly. Preserve
original mesh.ply/mesh.json and all current accepted numerical semantics.

Reconciliation found remote bounded acquisition
dd7661d8bff789a5de3b88addb4ea88370466ea7 above mesh
b4f89fa04dd97622db9a21c3d33188e5086efa51 and point cloud
97b8f5ad6cbe6cac218dac48c6b3d6f8036f91a3. Its 392-file divergent stack and
candidate-only protected-component/native-consumer dependencies are not adopted;
the acquisition head has no returned PR or Actions qualification. The candidate
also documents float32 ASCII double rounding in a third-party reader. Preserve
the accepted parser and use authored independent native-value oracles; do not
claim generic plyfile ASCII compatibility or add binary conversion by accident.
Sequence v1 stays unchanged; point clouds, volumes, physics and 3D training are
outside this increment. A12 cannot mark all M5 accepted.

## Acceptance and integration

Workers commit/push runnable checkpoints with source-bound original screenshots,
commands, fixture labels and precise pending gates. Root and reviewer inspect
actual screenshots. Representative evidence uses the available local PostgreSQL
17.11, app Python 3.12, optional pinned CPU runtime, Chromium and Node24; no user
computer. Share service configuration, never secret file contents. Offline
transport evidence retains the documented libc guard limits.

Before acceptance: focused owner tests and meaningful independent reader/oracle
checks; actual browser keyboard/navigation/repeated/empty/error/loading/stale
actions and responsive/native zoom; applicable existing image/text/WAV/mesh/
sequence regressions; independent exact-source review; and automatic feature
PR CI. Preserve old published results and migration/backup instructions. No
duplicate full run after an unchanged qualified source. Keep failed evidence
and scoped repairs visible. A demonstrated schema need, different target
granularity, missing cancellation ownership, broader format/physics requirement
or invalid family/precision proof triggers replanning before expansion.
