# Generic project CLI verification, 2026-10-14

Scope is generic CLI execution and compatibility, not a reproduced pressure
surrogate. All production source changes are the new CLI; existing project,
recipe, actor, runtime, Pipeline, Runs and UI contracts remain unchanged.

## Environment and source

- Base: Tuldok d856a984535a430909761ed13ce42eadd55b0710.
- Linux x86-64, CPython3.12.14, PostgreSQL17.11, psycopg3.3.6.
- A new disposable cluster at `/workspace/tuldok-test-pgdata` listens only on
  the private `/tmp/tuldok-test-socket` Unix socket, port55432; database `tuldok_test`.
  No existing catalog/service was selected. PostgreSQL packages were downloaded
  through signed Debian trixie indexes and extracted into `/workspace`, without
  system writes. The configured snapshot endpoint failed HTTP403; the ordinary
  Debian endpoint succeeded. Provisioning is a test dependency, not app behavior.
- Optional agent environment was installed explicitly with the unchanged
  `requirements-agent.lock` and `--require-hashes`; JSON Schema4.26.0/MCP1.30.0.
  `pip check` reports no broken requirements.
- Chromium151.0.7922.173 performed the unchanged external browser workflow.
- Read-only lab: e8a90bfef6b2955c502008ccc62443e29dd9f2ec.
  train_cpu.py SHA256 ee384926b3e3326356aa6c9b033b53c3c3236117514c848c2ebfc3a413115c37.

For Python database commands below, the explicit test DSN was:
`host=/tmp/tuldok-test-socket port=55432 dbname=tuldok_test user=agent`.

## Observed checks

| Command | Observed outcome | Claim/limit |
| --- | --- | --- |
| `.venv/bin/python -m unittest discover -s tests -p test_project_cli.py -v` (before rename) | 7 tests passed, 9.137s | Actual CLI subprocess→HTTP→PostgreSQL→production custodian→exact artifact download; negative authority and file publication |
| `.venv/bin/python -m unittest discover -s tests -p 'test_external_*.py' -v` | 28 tests passed, 58.942s | Existing admission, grants, cancellation, ambiguity, restart, streams, checkpoint summaries and artifact custody |
| `.venv/bin/python -m unittest discover -s tests -p test_artifact_segments.py -v` | 5 tests passed, 7.846s | Whole hash, corruption, mutation, revocation and segment authority |
| `.venv/bin/python -m unittest discover -s tests -p 'test_agent_*.py' -v` (before rename) | 23 tests, 21 passed, 2 explicit skips, 24.995s | Existing AgentClient parity/framing/auth; classifier runtime and optional MCP workflow were not then selected |
| `.venv-agent/bin/python -m unittest discover -s tests -p 'test_agent_*.py' -v` (final hash-pinned optional environment) | 30 tests, 29 passed, 1 explicit classifier-runtime skip, 45.611s | Includes all7 new CLI tests and real MCP/HTTP/domain workflow; no classifier or pressure-model qualification |
| `node tests/test_workspace_external_controller.cjs` | Passed | Mock transport controller projection/fences, not execution acceptance |
| `PATH="$PWD/.venv/bin:$PATH" BROWSER=/usr/bin/chromium node tests/browser_workspace_external.cjs` | Passed all four workflow checks | Real keyboard graph editing, owner review, stale input refusal, real descendants, agent grant, cancellation and restart/download |
| `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /workspace/Tuldok/.venv/bin/python -m unittest discover -s scripts -p test_train_cpu.py -v` in read-only lab | 6 tests passed, 0.031s | Gradient, gauge, train-only normalization, layout, optimization loss decrease and radius-one limitation; authored tiny data, not Rheon reproduction |
| Python compileall, JS syntax, `git diff --check` | Passed | Supporting source checks |
| Adopted `standards_verifier.checks.plan_contract.validate_plan` | Passed | Structural plan validation, not Standards Engine certification |

The renamed `tests/test_agent_project_cli.py` is selected by the existing optional
agent CI pattern. Its HTTP tests explicitly skip when the optional JSON Schema
dependency is absent; such a skip is never acceptance. The five publication
tests remain standard-library checks. Final pinned optional-environment results
are recorded in the execution ledger.

The first negative test incorrectly expected403 for an unknown grant. The
production owner returns404; the test was corrected and the full CLI set passed.
The first structural-validator invocation lacked its package root on PYTHONPATH;
supplying both actual package paths corrected the import failure. No failed check
was waived.

## Browser receipt

Actual neutral Run: `853c589a56e3406881f607d97c2cca90`.
Input/output SHA256: `1e4e0965a0a773437c393cfcd99d6c3794d6092fb22ba929f8557e822f653b68`.
Original local screenshots/receipt remain in ignored
`build/qa/workspace-external/run-406nNF`. They cover neutral production UI execution;
they are not screenshots of a neural Run or a claimed trained checkpoint.

CLI tests separately assert that its created graph appears in the production
Pipeline owner and that its completed attempt is the sole production Run. No
new UI implementation was added. Existing real progress tests verify declared
checkpoint/summary output hashes; the unchanged controller tests cover their
UI projection. This composition establishes shared-owner visibility, not a new
neural user-workflow acceptance claim.

## Standards and remaining evidence

Relevant template, workflow, Architecture, Contracts, Security and structural
validator files are identical between adopted dcc56f26 and available standards
HEAD188beda1. Source review confirms one HTTP validation/authority owner, no
new execution grants, automatic retries, schema versions, model loading or
duplicate queues. Local artifact publication is exclusive and uses the existing
whole-file verifier. No application-purpose Standards Engine was exposed.

The lab's NumPy CNN has actual gradients/Adam and is a suitable adapter reuse
candidate. Its local receptive field cannot by itself reproduce the existing
global pressure model's qualification. ModalPressure.fit is closed-form with
optimizer_steps0. Full neural training from captured lab datasets, persisted
split/weight evidence, fresh-process restore/evaluation and any numerical
pressure acceptance remain pending the paired lab owner's tested sources/data
and parent coordination. No GPU, remote worker, speedup or new physics claim is made.
