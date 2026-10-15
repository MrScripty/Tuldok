# Local implementation verification

Date:2026-10-15 UTC. Branch `feat/issue59-local-mcp-observer`, based on fresh
origin/main `f7543fb78f6f1cb52e45dd315efa17a4b2fe6fa6`. Preparatory commit710c404,
implementation checkpointce1ecbc; subsequent local evidence/fix commit owns the
final handoff. No push, PR, comments, deployment, merge or existing installation
activation. Environment health verified after parent-reported disconnect; no work
loss observed. Checkpoint commit preserved the implementation before final checks.

## Result and limits

Opt-in observer implemented locally. Reference #3 exacthead4887b7af was inspected
and admitted by parent from its local qualification/review. Hosted reference CI
remains pending and parent-owned; reference is not called merged or fully
CI-qualified. Tuldok publication remains unapproved. No hosted Tuldok CI is claimed.
[Reference admission](reference-admission.md) records reuse and deviations.
[Operating contract](../../../contracts/mcp-observer.md) owns all runtime limits.

| Check | Result | Evidence |
| --- | --- | --- |
| Observer storage/process suite | 22 passed, no skips,27.281s | [Log](observer-final.log) |
| Existing MCP boundary suite | 16 passed, no skips,9.967s | [Log](mcp-final.log) |
| Existing agent discovery/API/HTTP/domain/CLI/workflow plus observed real workflow | 31 passed, no skips,63.523s | [Log](agent-final.log) |
| Scoped access/HTTP/one-use approval/external execution/artifact segments | 39 passed, no skips,56.623s | [Log](authority-final.log) |
| Separate plain and observed real SDK→HTTP→PostgreSQL→neutral execution workflow | 2 passed, no skips,23.966s; also included in agent31 | [Log](workflow-final.log) |
| Independent GPT-6.1 Sol High source/privacy/lifecycle review | Final report owns exact disposition/hash bindings | [Review](implementation-review.md) |
| Diff whitespace and adopted structural plan checker | Passed; structure only, not acceptance proof | Final local checks |

The22/16/31/39 runs are distinct suite selections; API17 and workflow2 are
subsets of agent31 and are not added again as independent case counts.
No whole-repository/scientific/GPU/model qualification or release acceptance is
claimed. Tests use synthetic private stores, tokens and authored fixtures only.
No interaction database or actual telemetry is a deliverable.

## Deciding observations

- A1: real cold SDK initialize/list/call enabled versus disabled has byte-for-byte
  identical captured replies. Independent SQLite readback proves three generated
  correlations, correct ordinal/session/operation/schema identity, duration and
  exact input/output newline byte sums. Public registry v1 remains digest
  `cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8`,
  56 tools; tool-schema fingerprint
  `deeb2a54844707e6bc1c27df98e489b41123cd251283a9bc1d8007ec5f0d779a`.
  `agent_api.py` and PostgreSQL/domain source are unchanged.
- A2: unknown methods/tools, malformed argument kind/schema, invalid JSON, overlong
  input and partial EOF have one correlated terminal each, without dispatch.
  Duplicate/busy refusals remain separate while the original call runs; legal ID
  reuse creates distinct observer IDs. Typed transport/permission/domain/output
  validation/bridge cases preserve existing outputs with fixed metadata only.
  The observed real workflow verifies successful import mutation once, 401/403
  refusals,409 domain errors, external grant replay/restart and unchanged envelopes.
- A3: actual SIGKILL after independently read committed dispatch leaves an unmatched
  start across replacement; another live session is not rewritten. Broken stdout
  and actual pipe backpressure timeout retain unknown delivery and actual partial
  byte progress, independently of a successful returned stage. Oversize output
  substitution counts the small final frame and distinguishes HTTP200 from the
  synthesized502 envelope. Abrupt initialization exit rolls back before reopen.
- A4: every installed operation is projected with secret sentinels in raw IDs,
  unknown keys and nested content; raw SQLite bytes/sidecars and health output
  exclude them and their SHA256 values, including after retention. Real workflow
  tokens, catalog IDs, paths, raw text, annotations/output and source references
  do not appear in observer storage. No dynamic keys or scalar contents are
  traversed. Exact source identity binds canonical filename→per-file code digests.
- A5: actual locked, unavailable/unwritable, unsafe and quota-full SQLite exercise
  fail-open ownership. Locked/unavailable bridge replies equal disabled replies.
  Actual SQLITE_FULL is induced in the recorder transaction immediately after
  the authored client return, without mocking a raised SQLite exception: one
  dispatch, unchanged200 reply, degraded health and unfinished begin. It is a
  storage fault fixture, not a real domain commit/physical disk exhaustion claim.
  Broken diagnostics are guarded. Main/config tests prove opt-in/default-disabled,
  fixed sanitized configuration failure and basic operator persistence checks.
- A6: real multi-process first-open/writes respect bounded lock contention (a loser
  may degrade), reopen preserves sessions, count/age retention bounds starts and
  sessions, live-start eviction drops only late stages, and active in-memory state
  is bounded. Offline maintenance refuses active writers and never creates missing
  files. Unsupported/future/foreign/nonpristine/WAL/partial/corrupt stores and bad
  policy/orphan records remain byte-preserved on refusal. Integrity checks prove
  selected SQLite/schema/FK invariants, not tamper-proof arbitrary manual row data.
- A7: full required existing suites pass; classifier skip from preparation is now
  resolved using an explicit disposable actual scikit-learn runtime. No dependency
  manifests, lockfiles, lab/training source or original branches changed.
- A8: independent review catches/fixes are recorded in the exact-source report;
  local acceptance is conditional on its final satisfied disposition.

Frame byte claims cover observed bytes: complete lines include newline;
overlong unterminated frames count a bounded prefix, not unknown unread bytes.
Kernel write acceptance is not client receipt. Starts lost before telemetry commit
can leave no record; no event counts are an exact census. Age retention is driven
by new begins/offline maintenance; no idle timer.20ms is SQLite lock timeout,
not a hard limit on stuck filesystem/stderr I/O. No intent, task completion,
model tokens/billing, reconstruction/replay, telemetry export or analytics claims.

## Reproduction environment

Debian13/POSIX, CPython3.12.14, SQLite3.53.1. Agent interpreter:
`/workspace/issue59-agent-env/bin/python`, installed unchanged optional dependency
lock with `--require-hashes` plus existing app requirements. MCP1.30.0,
AnyIO4.15.1, jsonschema4.26.0, psycopg3.3.6, Pillow12.3.0.
Disposable selected classifier interpreter `/workspace/issue59-classifier-env/bin/python`:
scikit-learn1.7.2 (already declared training requirement), NumPy2.5.4,
SciPy1.18.1, threadpoolctl3.7.0, Pillow12.3.0. No production runtime configured.
PostgreSQL17.11 task-owned container `tuldok-issue59-postgres`, loopback55459,
image `postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3`,
no host data mounts. Only temporary test catalogs used. Fixture stopped at handoff.

From Tuldok root, with `TULDOK_DATABASE_URL` set to that disposable local service:

```sh
/workspace/issue59-agent-env/bin/python -m unittest discover -s tests -p test_mcp_observer.py
/workspace/issue59-agent-env/bin/python -m unittest discover -s tests -p test_mcp_stdio.py
TULDOK_TRAINING_PYTHON=/workspace/issue59-classifier-env/bin/python /workspace/issue59-agent-env/bin/python -m unittest discover -s tests -p 'test_agent_*.py'
PYTHONPATH=tests /workspace/issue59-agent-env/bin/python -m unittest test_access test_access_http test_execution_approvals test_external_runs test_artifact_segments
```

The adopted `standards_verifier.checks.plan_contract.validate_plan` checks plan
structure using the adopted standards clone root plus `tools/standards_verifier`
on `PYTHONPATH`; no Engine certificate or normative upgrade is claimed.

## Handoff

Retain this clean local feature branch for parent review/publication decision.
Do not push, PR, merge, deploy, enable telemetry, rewrite history, or retire the
branch without the applicable parent/user disposition. No Tuldok worktree was
created; protected training/lab work was not touched. Reference sources, isolated
interpreters and test image are local verification resources, not tracked payloads.
