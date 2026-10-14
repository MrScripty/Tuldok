# Independent preparatory review

**Date:** 2026-10-14
**Disposition:** Preparatory changes reviewed; no unresolved material findings.
**Implementation acceptance:** Blocked. This review does not qualify an observer
implementation, privacy guarantee, storage contract, or Coding-Standards #3 reference.

## Exact scope

Reviewed the local preparatory proposal on `feat/issue59-local-mcp-observer`
against Tuldok base `f7543fb78f6f1cb52e45dd315efa17a4b2fe6fa6`:

- The complete `tests/test_mcp_stdio.py` diff and its subprocess helpers.
- `docs/plans/mcp-observer/plan.md`, `issues.md`, `execution-ledger.md`,
  `reports/investigation.md`, baseline report and available baseline logs.
- Unchanged `mcp_stdio.py`, particularly profile admission/correlation,
  validation, dispatch, final encoding, stdout delivery and shutdown.
- Adopted standards in `/workspace/issue59-standards-reference` at
  `dcc56f26e884ade260770beceba2501d3746200d`: Core/Router and the applicable
  implementation, planning/discovery, proportionality, verification/oracle,
  IPC, contracts, diagnostics, security and concurrency guidance. Compatibility
  index files were treated as navigation, not normative testing policy.

This reviewer wrote only this report. No production changes, Git mutations,
external writes or publication were performed. The final test diff changes
only tests and the authored child fixture; production remains unchanged.

Reviewed material identities (SHA256):

| File | SHA256 |
| --- | --- |
| `tests/test_mcp_stdio.py` | `b48723182427a62d8dcc38a11a9207d07abe47b0c2104052b4ba5d0cd26173e4` |
| `mcp_stdio.py` | `9c4144cbb50d1144b3989ef8d71ac47e5a57e595cdf94253a5611feea1671362` |
| `reports/investigation.md` | `175bdd2df07155cf57459c9cff827963b96982a99efe991405f6ce9a8ff4c0bf` |

## Findings and verified dispositions

### PR1 — P2: Duplicate-pending regression depended on parent scheduling

The original new test used `TULDOK_TEST_DELAY='0.3'` and two separate parent
writes. A scheduling pause before the second write permits the original request
to complete, making the second use of ID 2 valid. The test then fails while
the bridge behaves correctly. A reviewer-injected 0.6-second pause reproduced
`StopIteration` at the null-ID refusal lookup.

**Resolved:** The authored child now waits for a test-only temporary release
file, with a ten-second deadline. The parent releases it only after asserting
the duplicate refusal. Cleanup terminates the child before removing the
directory. The same 0.6-second perturbation now passes, as do all three added
tests. This fix introduces no production hook.

### PR2 — P2: Dispatch entry was an insufficient durability oracle

The original interruption design signaled authored-client dispatch and killed
the process before asserting durable begin evidence. Dispatch entry does not
prove an asynchronous observer queue has committed that evidence. This could
reject a conforming reference or misclassify permitted pre-commit loss.

**Resolved:** [Investigation](investigation.md) now requires independent
readback of a committed begin before the recovery interruption. It separately
classifies kill-before-commit observation loss under the admitted durability
contract. The source wording was inspected; these future tests have not run.

### PR3 — P2: Authored `serve()` children cannot qualify operator activation

The initial acceptance design selected children invoking `serve(AuthoredClient())`.
Those children bypass `main`, actual configuration and authenticated bootstrap,
so they cannot establish the operator opt-in/default-disabled requirement or
sanitized configuration failure behavior.

**Resolved:** [Investigation](investigation.md) now explicitly requires the
actual `mcp_stdio.py --config` entrypoint, temporary private configuration and
local HTTP bootstrap. It covers default-disabled absence of observer files and
worker, explicit enable/disable, and sanitized health/configuration failures.
The final interface remains reference-blocked. This is a verified test-design
correction, not execution evidence for the future capability.

## Verification and limits

Reviewer execution used `/workspace/issue59-agent-env/bin/python`, importing
the existing test module without modifying it:

- Final three added subprocess regressions: **3 passed** in 1.951 seconds.
- Final duplicate-ID test with a 0.6-second pause before the duplicate send:
  **1 passed** in 1.241 seconds.
- Before the gate fix, that identical perturbation failed at the expected
  refusal lookup. This is a sampled scheduling counterexample, not a claim of
  exhaustive scheduling coverage.

Parent-provided full-run logs and [baseline](baseline.md) remain the owners of
broader test execution evidence. The recorded classifier-runtime skip remains
unqualified; a skip is not acceptance. Existing baseline tests and authored
protocol clients cannot establish observer persistence, domain authority,
universal protocol conformance or comprehensive privacy.

The preparation correctly distinguishes refused frames from dispatched work,
avoids raw client-ID correlation, separates domain return from actual encoded
delivery, and records privacy hazards before introducing persistence. It does
not advertise an implemented observer. Storage/configuration/lifecycle choices
must still be admitted from the parent-supplied qualified #3 source and its
acceptance evidence. Actual implementation requires a separate independent
source/privacy/lifecycle review and the planned direct acceptance evidence.
