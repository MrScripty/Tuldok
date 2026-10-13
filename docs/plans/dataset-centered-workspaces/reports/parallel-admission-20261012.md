# Parallel implementation admission — 2026-10-12

The user requested continued Tuldok development with multiple parallel agents.
The delegated scope admits integration review, one complete text training path,
and a separate WAV import/playback/timed annotation/export increment. This is
`continue` against `docs/plans/dataset-centered-workspaces/plan.md`, whose state
is Active/partial. The admitted source is
`6d939359d3cef2464c2aff990dd58d50c4f8d791`; remote main remains
`1bb2c3ae9d08432c53ddf9d4bf77fa5f62ad318c`. Both were read before implementation,
and the source checkout was clean. Adopted standards remain
`dcc56f26e884ade260770beceba2501d3746200d`; no Engine certification is claimed.

## Ownership and isolation

All proposals start from the admitted source in separate worktrees. Root is the
single shared-contract, active-plan and serial integration owner. Candidates
cannot authorize their own integration. Root rechecks source, changed shared
contracts, dependencies and evidence before integrating a complete branch;
published history is preserved with merge commits where topology carries
review ownership. No force pushes or main merges are admitted.

| Owner | Branch | Candidate write set | Dependency / integration target |
| --- | --- | --- | --- |
| Integration reviewer | `review/workspace-integration-20261012` | Integration report and report-prefixed evidence only | No implementation prerequisite; root integration branch |
| Text worker | `feature/workspace-text-runs-20261012` | New text trainer/export owner and tests; closed recipe dispatch in pipeline/runs; narrow app, release and workspace UI changes; text contract/report | Existing schema 2 suffices; root integration branch |
| Audio worker | `feature/workspace-audio-data-20261012` | New audio source/export/editor owners and tests; narrow workbench, immutable-asset accounting, release, app and classic Data UI changes; audio contract/report | Explicit schema 3 audio-kind extension; root integration branch |
| Storage worker | `feature/workspace-audio-schema-20261012` | Versioned metadata/upgrade and retained backup/migration compatibility; focused metadata tests and storage contract/report | Root-admitted schema 3 contract; audio then root integration branch |
| Root | `integration/workspace-next-20261012` | Active plan/ledger, shared documentation, CI registration, serial app/release/UI reconciliation and integration evidence | Reverify each candidate against current authority before integration |

Candidate overlap in `app.py`, `dataset_releases.py` and classic Data controls
is deliberate branch isolation, not concurrent mutation of an authoritative
working tree. Text alone extends graph/run semantics; audio does not add a
second run owner. Storage alone owns the schema extension. Workers do not
modify the canonical plan, global README or CI registration. Branches and
worktrees remain owned implementation proposals pending final disposition;
cleanup must preserve exact accepted or retained commit reachability.

## Bounded text contract

Reuse text-classification annotation/review, source-family allocation and
release-preview authority. A narrow `text_classification_v1` export is needed:
the existing mixed canonical ZIP does not publish the complete protected-family
snapshot required by the standalone trainer reader. Do not weaken the proof or
change existing canonical/image formats. Freeze exact source/content hashes,
annotation references, labels, split rows and protected-component snapshots.

Fit pinned scikit-learn TF-IDF plus MultinomialNB using train rows only. The
candidate bounds are 6–512 records, 2–8 labels, each label represented in all
three splits, 8 MiB ZIP, 16 MiB expanded bytes and 16 KiB per text. Editable
parameters are bounded vocabulary size and smoothing. The result model uses
closed JSON arrays/vocabulary, never executable pickle. Preserve retained image
graph/run contracts and make image/text dispatch explicit and closed. No new
weights, external inference, automatic dependency install or arbitrary commands.

Acceptance requires a real browser import/review/freeze/edit/save/train/results
path, actual train-only fitting and independent model/result reading, immutable
IDs/hashes and test exposure, reload/restart recovery, invalid/stale cases,
keyboard/narrow layout, screenshots, and affected image regressions. Tiny authored
inputs prove the workflow and do not establish useful model accuracy.

## Bounded audio and storage contract

Import original bounded PCM WAV bytes into managed local filesystem assets.
Reuse records, review history, rights, source revisions and protected families.
Sample-frame intervals are half-open integers with explicit channel identity;
playback/peaks must preserve channel/rate semantics. Text/class/speaker fields
are human annotation, never a claim of ASR. No resampling, inferred transcripts,
compressed-codec expansion or audio training.

The existing PostgreSQL kind CHECK excludes audio. A separate explicit schema
3 upgrade widens that constraint and retains exact version-1/version-2 reference
definitions. Known old catalogs require stopped-writer upgrade; startup never
mutates them. Prove retained backup/restore, legacy SQLite import, version and
drift refusal, atomic rollback, and idempotent explicit upgrade. No new store or
personal-data migration is admitted.

The first audio increment is runnable Data import/playback/timed annotation,
review and frozen export, independently read using known stereo impulses. Test
interval/channel bounds, unsupported encodings, draft/stale refusal, reload,
keyboard and narrow layout. Full audio Pipeline/Runs validation/export remains
a later M4 gate; a Data-only increment must not mark all M4 accepted.

## Review and publication

Preserve PR32/33 as separate drafts. Inspect their exact overlap and failing
Pumas gate without assuming the same failure signature proves identical cause.
Do not copy duplicate compact UI or waive failures. The finished M1/MB/M2 source
already passed exact-head lifecycle CI38181666802 (98 successful steps, no skips)
and focused CI38181666836. New proposals require their own focused evidence,
independent review and applicable integrated CI before acceptance.

Publish committed feature checkpoints and an integration draft PR. No main
merge/deployment is admitted. Do not run on the user's computer or external
Codex Cloud harness. Local optional CPU packages and disposable PostgreSQL
fixtures are authorized; large model weights and paid services are not.
