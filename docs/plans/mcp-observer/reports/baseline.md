# Preparatory baseline

Tuldok base: `f7543fb78f6f1cb52e45dd315efa17a4b2fe6fa6` (fresh origin/main).
Branch: `feat/issue59-local-mcp-observer`. Production code remains identical to
base at this checkpoint. Test-only changes add three MCP boundary cases.

Environment: Debian 13 POSIX, Python 3.12.14, SQLite 3.53.1. Isolated interpreter
`/workspace/issue59-agent-env/bin/python`; optional requirements installed with
`pip install --require-hashes -r requirements-agent.lock`, then existing
`requirements.txt`. Actual versions: MCP1.30.0, AnyIO4.15.1, jsonschema4.26.0,
psycopg3.3.6, Pillow12.3.0. No manifest/lockfile changes.

## Completed checks

| Command (from repository root) | Result | Evidence |
| --- | --- | --- |
| `$PYTHON -m unittest discover -s tests -p test_mcp_stdio.py` before edits | 13 passed, no skips | [Log](baseline-mcp.log) |
| `$PYTHON -m unittest discover -s tests -p test_agent_api.py` before edits | 17 passed, no skips | [Log](baseline-agent-api.log) |
| `$PYTHON -m unittest discover -s tests -p test_mcp_stdio.py` with preparatory cases | 16 passed, no skips | [Log](preparatory-mcp.log) |
| `$PYTHON -m unittest discover -s tests -p 'test_agent_*.py'` with isolated PostgreSQL | 30 discovered; 29 passed, 1 skipped | [Log](baseline-agent-integration.log) |
| `PYTHONPATH=tests $PYTHON -m unittest test_access test_access_http test_execution_approvals test_external_runs test_artifact_segments` with isolated PostgreSQL | 39 passed, no skips | [Log](baseline-authority-execution.log) |
| `git diff --check` | passed | Local diff check |

`$PYTHON` denotes the isolated interpreter above. These are existing behavior and
preparatory regression observations; they do not establish observer persistence,
privacy, failure, lifecycle or reference qualification.

## Public identity

Computed by importing unchanged `agent_api` and hashing its public encoded tool
catalog, using `hashlib.sha256(agent_api.encoded(agent_api.tool_definitions()))`:

- Registry version: `1`
- Registry digest: `cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8`
- Tool count: `56`
- Tool definitions SHA256: `deeb2a54844707e6bc1c27df98e489b41123cd251283a9bc1d8007ec5f0d779a`

These are code/public schema identities, not sensitive content hashes.

## Real domain test environment

Task-owned disposable PostgreSQL17.11 fixture in container
`tuldok-issue59-postgres`, loopback port55459, no host data mounts. Image identity:
`postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3`.
Only this fixture receives `TULDOK_DATABASE_URL`; no existing installation is used.
Agent/workflow/domain/CLI tests completed as above. The one skip is
`test_scoped_agent_exposes_actual_completed_authored_classifier_holdout`, which
requires an explicitly selected `TULDOK_TRAINING_PYTHON` with a real classifier
runtime. No such runtime was present or selected. This training-specific claim
remains unqualified; a skip is not acceptance. Fixture is stopped at the
preparatory checkpoint; rerunning requires
creating this isolated test service again. Disposable fixture credentials are
local test data, never application/operator credentials.

The adopted `standards_verifier.checks.plan_contract.validate_plan` returned no
error for this plan. Run with the standards clone root and its
`tools/standards_verifier` directory on `PYTHONPATH`; this checks plan structure
only and does not qualify the blocked observer design.
