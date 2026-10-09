# Independent bulk Rheon design review

Reviewed the plan against base `c93aee448e60b310eb5f9d926fa4185130e91a6d`, including
`rheon_sequences.py`, `sequence_assets.py`, `immutable_assets.py`, Workbench save
and history ownership, HTTP admission/error handling, and the existing collection,
single-sequence and raw-bulk controllers. Read-only review; no implementation,
simulation, provider execution or public mutation. No applicable local AGENTS or
skills were found.

**Admitted for implementation with the requirements below.** No fundamental
composition or lifecycle blocker was found. The small SequenceAssets extension
can place trusted acquisition context in its existing origin before immutable
asset/record/history publication. Workbench human sequence review preserves that
origin and enforces trajectory/initial-family groups. Collection `refresh()`
does not replace the editor or mutate the selected-record map.

1. Store the context only at `provenance.sequence_acquisition`; retain the existing
   simulation origin and adapter hashes. Check marker uniqueness and call admission
   under the same reentrant Dataset lock. Put the marker in the initial origin,
   never a post-admission update. Validation may happen before that lock. Injected
   asset/record/history failures must roll back the marker too. Classify storage
   failures as uncertain/server failures; the existing HTTP fallback can otherwise
   turn an OSError into a 400 and incorrectly permit continued scheduling.
2. Lookup must require sequence kind and exact `tuldok_rheon_batch_v1` format,
   fetch at most two matches to detect ambiguity, and return bounded admission
   identity/context/hash evidence without loading a bundle or arrays. Do not reuse
   raw `bulk_import.find_result`, whose namespace and row assumptions differ.
   Neither lookup nor its receipt certifies current source integrity or review.
   Client confirmation must bind marker, exact declared labels/index and both
   hashes of the bytes actually encoded for the POST; mismatches remain uncertain.
3. Preflight the entire selection before any contents read: one common root,
   exact three-component relative paths, complete unique pairs, exact bounded
   labels, file counts and positive per-file/aggregate sizes. Snapshot all files
   and controls before awaits. Read each file once and retain only the current
   pair's encoded/raw working data. The 32-pair/40 MiB selected-raw limits are
   browser admission bounds, not a server-wide quota across independent POSTs.
   Preserve the independent 40 MiB immutable-bundle selection/export budget,
   including ZIP overhead. The new HTTP route needs its explicit 3 MiB cap and
   closed UTF-8 JSON envelope, rejecting duplicate fields and invalid constants.
4. Stop checks must follow asynchronous reads/hashes and precede every POST.
   Pagehide must stop future scheduling and fence stale read, POST, lookup and
   final-refresh continuations; it cannot undo an in-flight commit. Prevent
   repeated controls/held responses from acting on a newer batch. A missing GET
   result is inconclusive and keeps the pending item; confirmation never resumes
   later pairs. Reload recovery is explicitly not durable. Dismissal makes no
   rollback claim. Keep acquisition outcomes separate from a failed collection
   refresh so a known committed receipt is not reclassified as a rejected item.
5. Keep new draft state, permission notes, parents, human review, fixed selection
   and whole-family export with their existing owners. Labels remain inert
   declared context; only an explicit user group links otherwise unrelated runs.
   Tests must retain dirty editor contents and exact selection snapshots, not
   merely check that their panels remain visible.

The planned SQLite/reopen, malformed producer fixture, race/failure, controller
and actual selected-file Chromium coverage is appropriate. Add explicit checks
for simultaneous marker collision, a marker borrowed from the raw-import
namespace, pagehide during a read/held POST/lookup, and refresh failure after a
valid creation receipt. Independent implementation review and exact-head full
qualification remain required before completion.

The producer PR20 head has advanced to
`3bf61ba85d066cadb95cddffb29a2b40fe497ccf` according to the parent's fresh supported
read. This slice deliberately keeps the admitted exporter/validator and retained
actual fixture at `fee7b4a139574f87b259796b1ba8698a41d31ac1`. No newer contract is
accepted by this review; adoption requires separate root-coordinated review.
