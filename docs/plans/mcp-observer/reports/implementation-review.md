# Independent implementation review

**Date:** 2026-10-14–15 UTC

**Review role:** Requested independent GPT-6.1 Sol High source/privacy/lifecycle review.

**Source disposition:** Satisfied for the exact material bound below; all findings resolved.

**Qualification boundary:** Local implementation review only. Broader owner-run
verification, plan acceptance and publication remain separate decisions.

## Scope and authority

Reviewed the local Tuldok issue59 proposal against base
`f7543fb78f6f1cb52e45dd315efa17a4b2fe6fa6`, including the complete recorder,
bridge adaptation, observer tests, changed real-workflow test, README and operator
contract. Read the active plan, investigation, reference admission and available
baseline evidence. Adopted standards remain
`dcc56f26e884ade260770beceba2501d3746200d`; applicable review guidance includes
Core/Router, verification/oracles, planning, ownership, IPC, persistence,
contracts/evolution, security, diagnostics, concurrency and resilience.

The parent supplied qualified local Coding-Standards #3 revision
`4887b7aff0ba84acd257da081135b7849cc9c79f`. Read its verification and independent
review reports, actual recorder/MCP integration and operating contract. The
extracted recorder, MCP source and operating-guide SHA256 values match the
reference independent review's final bindings. Its license is CC0-1.0. This
review accepts the parent's local-reference admission; hosted CI remains pending.
Neither that reference nor Tuldok is claimed merged or fully CI-qualified.

No implementation edits, Git mutations, external writes, publication, deployment
or existing-installation enablement were performed by this reviewer. Independent
probes used synthetic temporary private SQLite stores and child processes.

## Findings and resolutions

| ID | Severity | Observed issue | Verified resolution |
| --- | --- | --- | --- |
| I1 | P2 | Offline health accepted an invalid persisted policy, and retention trusted it. Setting `max_calls=0,max_age_seconds=-1` caused a valid retained interaction to be deleted while both checks reported healthy. | Shared `_read_policy` requires exactly one row and the configured type/range invariants before writer admission, health or destructive retention. Regression verifies malformed-policy bytes remain unchanged. |
| I2 | P2 | `http_status` included bridge-synthesized statuses: connection failure became HTTP503 and invalid output became HTTP502 even when no such HTTP response existed. | Actual client-return status and `envelope_status` are separate. Transport exceptions leave HTTP status null; output validation/substitution preserve the returned status independently of the synthesized envelope. Typed subprocess evidence passes. |
| I3 | P2 | `check_store(missing, retain=True)` created a zero-byte file before rejecting it. Offline maintenance was unintentionally a store-creation path. | `_connect` defaults to no creation; only recorder startup explicitly permits creating a store. Independent repro now raises `FileNotFoundError` and creates nothing. |
| I4 | P2 | Reopening a store containing an orphan event reported healthy and appended observations, although operator inspection rejected the same FK corruption. | Shared SQLite quick-check/FK validation runs during recorder admission under writer isolation and before maintenance mutation. Independent repro now degrades with `invalid-database-records` and preserves the file byte-for-byte. |
| I5 | P2 | Implementation identity hashed concatenated file bodies without identifying their boundaries. Moving a suffix between modules could preserve the digest while changing module ownership/execution. | Identity hashes a canonical filename-to-per-file-SHA256 mapping. Construction inspection establishes that file names and boundaries now participate without introducing content-derived telemetry. |

The persisted-admission findings were repaired at shared owners consumed by
startup and operator maintenance, rather than only at the sampled failing call.
No unresolved source/privacy finding remains in this scope.

Test-review corrections also removed imported-TestCase double discovery, changed
cold parity from parsed-object equality to captured reply-byte equality, and
bounded/owned the concurrent fixture's release wait and child cleanup. Missing
acceptance scenarios identified during development were added for actual
main/config/bootstrap, typed outcomes, post-return SQLite FULL, partial stdout
timeout, final encoding substitution, simultaneous first-open and real observed
domain workflow. This report does not treat an initially absent test as evidence.

## Independent evidence

Interpreter: `/workspace/issue59-agent-env/bin/python` in the repository root.

```sh
PYTHONPATH=tests /workspace/issue59-agent-env/bin/python -m unittest test_mcp_observer
```

Observed **21 tests passed in 27.481 seconds**, without duplicated imported SDK
tests. This includes real SDK subprocesses, actual private SQLite stores and
actual kernel pipe delivery failure/timeout. HTTP-shaped authored clients prove
bridge classification; they do not independently establish domain authority.

After the final source-identity, concurrent-fixture and initialization-test delta,
the following independently executed **four tests passed in 5.773 seconds**:

- Interrupted initialization before publication and subsequent reopen.
- Simultaneous process first-open/writes with bounded owned children.
- Exact cold reply-byte parity, framing counts and registry/schema identity.
- Typed execution outcomes with distinct actual HTTP and envelope status.

The one newly added initialization test is included in that final delta run.
This is a 21-test complete-module observation plus focused final-delta evidence,
not a claim that the reviewer executed a later complete module in one invocation.
Independent synthetic reproductions also confirmed I1, I3 and I4 before their
fixes and confirmed the preservation/no-creation postconditions afterward.

The enabled real PostgreSQL/domain workflow test was source-reviewed: it retains
the existing workflow assertions and adds observation readback across mutation,
stale revision, permission refusal, restart and revocation. Its execution result
belongs to the owner's final verification evidence; this reviewer did not run
that domain fixture independently. The preparatory classifier-runtime skip was
subsequently resolved in the final owner-run evidence inspected below. Neither
synthetic tests nor these selected suites establish model intent, billing,
universal external conformance, whole-repository acceptance or hosted CI.

## Final owner-evidence addendum — 2026-10-15

Inspected [final verification](verification.md) and each complete log below.
These are owner-executed results independently read by this reviewer; they do
not replace or enlarge the reviewer's own execution claims above.

| Owner-run selection | Observed result | Log |
| --- | --- | --- |
| Observer storage/process module | 22 passed, no skips, 27.281 seconds | [Observer](observer-final.log) |
| MCP boundary module | 16 passed, no skips, 9.967 seconds | [MCP](mcp-final.log) |
| Agent API/HTTP/domain/CLI/workflows, including observed real workflow | 31 passed, no skips, 63.523 seconds | [Agent](agent-final.log) |
| Access/approval/external execution/artifact selections | 39 passed, no skips, 56.623 seconds | [Authority](authority-final.log) |
| Separate plain and observed real SDK→HTTP→PostgreSQL workflow | 2 passed, no skips, 23.966 seconds | [Workflow](workflow-final.log) |

The separate two-workflow run is a subset of agent31 and is not added again.
The selected disposable actual classifier interpreter resolved the preparation's
missing-runtime skip; the final agent selection contains no skips. This closes
that specific baseline evidence gap without implying whole-repository,
scientific/model-performance or release qualification. No dependency manifest,
lockfile, protected training/lab source or production runtime was changed.

Recomputed all six material hashes after reading the final evidence: every
source, test, operator-contract and README value still matches the table below.
The final evidence supports the planned local claims within their stated
observability and operating limits. Source/privacy/lifecycle review remains
satisfied with no unresolved findings. Reference hosted CI remains pending and
parent-owned; no publication, merge, deployment or full hosted-CI claim is made.

## Composition, privacy and lifecycle conclusion

The bridge owns actual framing, admission, SDK dispatch, encoding and byte delivery;
the recorder owns value-free projection, transactions, retention and fixed health.
Main alone configures opt-in. The domain/HTTP owners retain authorization,
mutation, retry and audit authority. There is no queue, background worker,
reporting product, new tool, domain registry or runtime dependency.

All observed attacker-controlled strings pass through a closed projection before
SQLite. Top-level keys require exact installed-schema membership; nested values
are not traversed, and sensitive subtrees are redacted. Raw IDs, paths, inputs,
outputs, errors and sensitive hashes have no persistence/health path in the
reviewed construction. Code/schema digests identify installed public material.

Generated identities separate legal ID reuse and duplicate/busy refusals from
the admitted request. Returned evidence is independent of terminal delivery;
partial writes retain actual progress and unknown delivery. Committed starts
survive SIGKILL without fabricated completion or cross-session repair. Count/age
retention removes dependent stages and orphan sessions; eviction drops late
evidence without disabling a healthy recorder. Exact schema, policy and selected
integrity proofs precede admission or maintenance publication.

These conclusions depend on the documented local POSIX/private trusted-directory
and coherent immutable-source preconditions. Same-user tampering, backup/device
remnants and client receipt are outside the promise. A 20 ms busy timeout bounds
SQLite contention only; synchronous filesystem/stderr I/O has no hard latency
guarantee. Fail-open loss and unmatched starts remain explicit. Operator health
is selected integrity/count evidence, not a semantic privacy audit of arbitrary
externally modified rows or an exact census of all interactions.

## Exact final material binding

| File | SHA256 |
| --- | --- |
| `mcp_observer.py` | `b4630f48db0365ab7bf724d9dc81e9dfa781dc8aad6314573ac172c0e6fd845d` |
| `mcp_stdio.py` | `7a87261212474b06dad85ab7f8ab8693c20cd0fec90ded0ba034f2adf0ced344` |
| `tests/test_mcp_observer.py` | `ef8b3d0b3ed6e1c351693c5a4c53cc8699fb26281bb1c062840d1a9430a75fe6` |
| `tests/test_agent_workflow.py` | `959788751b0de8af9fdb923621fe851c9965d6ae3012e165080aa677d1859df0` |
| `docs/contracts/mcp-observer.md` | `c54bb3c5708066b14e67de21dd456dc86726da2b7399042d0e7f5c625c648c11` |
| `README.md` | `af27417fcfe46b72f9865347d5a36f629921f53d05f870d9bc2b5005ace77dc3` |

Material changes affecting these reviewed claims require a scoped recheck.
Adding evidence or recording an unchanged lifecycle result does not invalidate
the reviewed source. The owner remains responsible for final evidence/plan
dispositions and retaining the explicit hosted-CI and broader qualification limits.
