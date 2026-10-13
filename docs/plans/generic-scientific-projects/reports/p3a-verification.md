# P3a scoped local actors

Branch `feature/scoped-local-actors-20261013` descends from qualified P2 commit
`2476a7daa339597557d29eb6e691327895d8c48c`. This checkpoint introduces the actor
boundary across existing operations. P3 remains incomplete until external process
custody and material execution approvals qualify in P3b. No merge or deployment.

## Implemented boundary

Schema 7 retains the exact schema 1–6 definitions and adds actors, hashed opaque
credentials, transactional audits and closed job admissions. Local CLI login
creates a private one-use code; browser exchange issues an expiring HttpOnly,
SameSite Strict cookie. HTTP and direct domain calls share explicit catalog-bound
actor checks. Missing, revoked, expired and cross-catalog credentials fail closed.
Mixed credential transports and explicit foreign origins are refused.

Agents receive only owner-issued scopes. Human review requires a current owner
and audits exact content and revisions; agent response drafts retain agent
attribution. All current generation, inference, verification and training starts
remain owner-only. Workers receive exact durable job receipts and finite effects,
not inherited owner scopes. Revocation stops new admissions; bounded admitted
work can finish. Startup reconciliation cannot admit or replay work.

The three browser entrypoints share compact session controls. Login never replays
a mutation, expired sessions retain edits, and stale identity responses cannot
replace a newer session. Forty-seven real browser suites and direct Python/CLI
callers use explicit production authentication; pure controller fixtures remain
isolated tests rather than authentication evidence.

## Evidence and review

- [Actual login browser receipt](p3a/access-receipt.json), [390px screenshot](p3a/session-390.jpg),
  [desktop screenshot](p3a/session-1280.jpg). Root inspected the narrow view.
  Existing workspace browser: all 18 checks pass (`run-qrJHY8`).
- Access/schema/storage focused regression: 40 tests pass; final Access-only
  rerun: 9 pass. Closed asynchronous job owners: 74 tests pass. Runs: 13 pass.
  Responses, rights and real HTTP access: 30 tests pass before the added response
  draft-denial assertions, which are included in the full run.
- Auth controller/helper tests pass, including Request-object mutation refusal,
  stale-session ownership and credential confinement to the exact application
  origin. Twenty-three existing JS controller suites pass.
- [Domain inventory](p3a/domain-guard-inventory.json), independent root/domain/UI
  reviews and plan-contract validation cover the shared boundary. Review fixes
  removed a public split mutation path, preserved authorization exceptions,
  audited transport refusals, and moved procedural execution admission before
  asset creation. Guards do not change existing transaction ownership.
- The disposable PostgreSQL fixture exhausted its 64 MiB POSIX shared-memory
  mount after accumulated test schemas. Switching only that fixture to mmap
  restored capacity without deleting schemas. Interrupted runs are not passes.

Full regression ran 708 tests in 643.073s: four failures and fourteen errors,
with two optional-reader skips. Fifteen failures were explicit-auth fixture
migrations; three exposed compatibility defects in the new boundary: structured
storage error codes, retained Unicode audit hashing and invalid preference-ID
guard targets. Those defects and all affected fixtures were corrected. The final
31-test rerun passes (all 18 failed cases, nine Access tests and four real HTTP
access tests). Independent point/volume readers pass all 20 tests, covering both
skips. No runtime source changed during the broad run; the final bounded source
corrections were independently reviewed. [Final source hashes](p3a/source-files.json)
bind the candidate. Hosted exact-head CI will rerun the full suite after publication. No static type-checker
or Standards Engine certificate is claimed. This milestone does not qualify ASR,
general 3D training, external process containment, remote deployment or scientific
model quality.

## Next-stage prerequisite

A scratch Linux probe demonstrated a start barrier, subreaper adoption of a
double-forked detached child, and pidfd-driven drain to ECHILD. Helper death left a
live descendant, requiring an unknown-state execution fence. The native Rheon
binary performed only an 8³ ready/stop exchange; no simulation/model acceptance
is claimed. `/proc/.../children` is unavailable, so the revised probe used PPID
scanning. An initial failed probe left a PID-1-owned zombie after its bounded
child exited; revised cases fully reaped their children. Production lifecycle
qualification is still P3b work, after P3a CI.

## Hosted regression correction

PR47 initial head4d3314a passed all14 workspace-UI steps and the full hosted Python
suite, new authentication browser gate and scientific/project browser gates.
Lifecycle run38431312561 then failed the legacy corner-studio viewport assertion:
the new session bar added height above an existing fixed-height workspace. A
scoped desktop CSS flex layout shares the viewport among session bar, header and
main content. The complete legacy browser passes locally with Chromium after the
fix, including its narrow-screen image-fit check and four local provider fixtures.
GitHub log retrieval returned403; diagnosis used local reproduction, not an
assumed failure cause. Final-head CI must repeat before P3b admission.
