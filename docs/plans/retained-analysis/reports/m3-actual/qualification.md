# Actual PostgreSQL and retained Run qualification

Date: 2026-10-20. This follow-up resolves the initial environment absence after
the parent confirmed ordinary disposable test infrastructure is in scope.
The earlier [12-pass/one-skip record](../m1/focused-tests.log) is unchanged.

## Observed boundaries

- Official Debian PostgreSQL 17.11 packages were downloaded and extracted under
  `/tmp/tuldok-pg-bin`; no system package or service was changed. The existing
  `scripts/local_postgres.py` owns the private service at
  `/tmp/tuldok-analysis-pg`. It listens on its private Unix socket only. The
  application role is not superuser and cannot create databases or roles.
- Repository-pinned Torch 2.8.0+cpu, torchvision 0.23.0+cpu and scikit-learn 1.7.2
  were installed in `/tmp/tuldok-training-runtime/venv`. The normal model-aware
  runtime probe reports available. [Environment](environment.json) records
  observed versions and official package hashes, without credentials.
- `tests/retained_analysis_actual_fixture.py` used the normal Dataset owner,
  six authored images, frozen release, Pipeline validation and supervised native
  classifier Run. Two epochs produced 22 retained artifacts. This is transport
  evidence, not a model-quality or scientific separation claim.
- [Fixture receipt](fixture.json) contains exact Run/result/artifact identities
  and source hashes. The retained catalog/artifacts remain in the task-owned
  directory `/tmp/tuldok-analysis-real-run`; its token is private and is never
  copied to a report or command argument.

## Results

The original query suite now passes **13/13**, including the formerly skipped
actual PostgreSQL SQL test: [log](original-query-tests.log).

The new actual retained-query suite passes **6/6**: [log](retained-query-tests.log).
It reads metric observations, checkpoint inventory, probe membership and
probabilities directly from original retained artifact bytes and compares them
against the actual SQL query output. It exercises all three metric definitions,
both checkpoints, stable paginated example IDs, support/error filtering, units,
inert query/export behavior, unchanged Run document/artifact hashes, restored
session timeout, real issued/revoked inspect credentials, artifact tamper
re-verification and a fresh Python process reopening the same exact result.

Final-check revocation uses an explicitly fault-injected timing wrapper around
Access.require; the revocation and credential check themselves use the real
Access owner and PostgreSQL. The repeated-tamper test restores exact original
bytes in finally. No verifier/authentication/query data is substituted.

Separate GPT-6.1 Sol High review found no blocking evidence/oracle defect. The
reviewer independently reran the original 13 tests and the three non-mutating
actual tests: **16 passed, zero skips**. It inspected the mutation tests without
repeating them, verified source/receipt hashes and private file modes, and did
not create another service, fixture or training Run.

Reviewed source SHA256:

| File | SHA256 |
| --- | --- |
| retained_analysis.py | 317ba63b0f89367ba26dd62b8157910654943eb8a9d3ab1442f09f09827f218b |
| tests/retained_analysis_actual_fixture.py | 5e8759c7715de85b8df886727d11335cc913d78d178b3d787e09778aab29ff55 |
| tests/test_retained_analysis_actual.py | 255abedd2980dd36deee27ae0a12c1f1e3870c3c92c3203bea334ae7bfd8e651 |

## Reproduce in this retained task environment

Select the task-owned PG binaries and normal helper environment, then run with
the base application dependencies and the existing fixture:

```sh
export PATH="/tmp/tuldok-pg-bin/usr/lib/postgresql/17/bin:/tmp/tuldok-analysis-venv/bin:$PATH"
eval "$(python scripts/local_postgres.py env --directory /tmp/tuldok-analysis-pg)"
export TULDOK_TRAINING_PYTHON=/tmp/tuldok-training-runtime/venv/bin/python
export TULDOK_ANALYSIS_ACTUAL=1
export TULDOK_ANALYSIS_FIXTURE=/tmp/tuldok-analysis-real-run
python -m unittest discover -s tests -p test_retained_analysis_actual.py -v
```

For a fresh task-owned instance, provision the ordinary repository requirements,
use the existing local-service helper with a new private directory, then prepare
one fixture explicitly. The preparation refuses an existing destination. Do not
point these fixtures at a production catalog or repeat training just to reopen
the retained result.

## Remaining acceptance

`tests/test_retained_analysis_http.py` and
`tests/browser_retained_analysis_actual.cjs` are prepared for the coordinated
new operation contracts/routes and Runs mount. They have syntax checks only;
they are **not yet executed or accepted** because those shared hooks have not
been approved/integrated. The HTTP test requires explicit
`TULDOK_ANALYSIS_HTTP=1`; it must fail if the exact new contracts are absent.
The actual-browser test uses normal app.py/authentication and retained data,
without test-only routes. Its selectors and operation paths must be confirmed
against the eventual agreed integration before execution.

The existing isolated renderer test remains actual Chromium evidence over
authored data. It does not become authenticated Runs evidence merely because
the direct query now passes actual PostgreSQL tests.
