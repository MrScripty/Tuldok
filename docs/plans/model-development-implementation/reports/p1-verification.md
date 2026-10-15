# P1 verification: compatible operation negotiation

2026-10-15. Source branch `feature/model-development-p1`, based on
`d788e08f3813af8b6bd054218556abb9e7df431c`. Local implementation checks pass;
committed-head CI and merge remain the next integration gate. This is transport
acceptance, not the later model-development objective acceptance.

## Delivered behavior and decisions

One registry preserves the exact56-operation f588 legacy discovery while new
clients negotiate exact ID/version/contract intersections. Selected requests
prove the method/path/query/injected body, strict JSON, bounds and complete
selected schema before domain entry. Current Access, grants, revisions and
receipt reconciliation remain authoritative. New clients ignore valid additive
operations and refuse only the incompatible requested operation. MCP lists and
validates the selected schema, including an older locally supported version.

Headerless legacy HTTP retains its wider grammar. New branches sharing any old
route template must explicitly require their selected operation before domain
entry. P1 adds no new model/task operation. Frozen legacy retirement requires an
owned supported-installation cutover. Future new-meaning submit versions must
bind their semantic contract in durable receipts; P1 retains one submit meaning.

The response ceiling is16MiB rather than the draft8MiB because the retained
8MiB artifact segment needs11,184,812 base64 characters. Manifest/request caps
are1MiB. Existing JSON Schema4.26.0 is a lazy base dependency; no custom schema
engine, MCP/Torch startup dependency or remote schema/code retrieval is added.

## Actual environments and procedures

- Disposable PostgreSQL17.11, official Debian packages extracted under `/tmp`;
  private Unix socket, no TCP listener, disposable catalogs only. No system
  service, user catalog or data migration was changed.
- Fresh private CPython3.12 environment installs base requirements and exact
  `requirements-agent.lock` with `--require-hashes`: MCP1.30.0, anyio4.15.1,
  jsonschema4.26.0, pydantic2.14.1, psycopg3.3.6, Pillow12.3.0.
- Separate private CPU environment installs `requirements-training.txt`:
  Torch2.8.0+cpu, torchvision0.23.0+cpu, scikit-learn1.7.2. Its explicit selection
  exercises the existing bounded authored text-classifier holdout test. No
  image-history profile, GPU or physics acceptance is implied.
- Existing Chromium/Node exercise actual authenticated Data/Pipeline/Runs
  project navigation, narrow/desktop layouts, keyboard opening, escaping,
  project isolation, browser reload and server restart.

| Procedure | Actual result | Proof and limits |
| --- | --- | --- |
| Pinned `unittest discover -s tests -p 'test_agent_*.py' -v` with disposable PostgreSQL and selected CPU runtime |50 passed,0 skipped;162.089s | Registry, all12 annotation tasks, HTTP custody/revocation,19 negotiation cases, CLI and real MCP workflow/restart/observation. Snapshot predates wrapper/max-segment additions; the following focused gates qualify those additions. |
| Retained/upgraded CLI and MCP subprocess old/new server matrix |2 passed,0 skipped;20.604s | Each test executes all4 peer combinations, including actual project-open mutation; no invented legacy client/stub replaces the retained source. |
| Actual maximum8MiB artifact segment via selected HTTP and official-SDK MCP |1 passed,0 skipped;17.557s | A real neutral Run produces8MiB, both paths return identical full bytes within existing response bounds. No model claim. |
| Pinned `test_mcp_stdio.py` |17 passed,0 skipped;16.011s | Framing, lifecycle, busy/unknown outcomes, output bound and selected older-schema/tool projection. |
| Actual `test_execution_approvals.py` |9 passed,0 skipped;2.105s | Existing atomic grants, real two-connection consumption and unknown-commit custody remain intact. |
| Actual project browser workflow |Passed | Existing read-only UI/source bytes/restart remain usable; retained receipt in ignored `build/qa/workspace-project/run-xJZzQx`. |
| Independent GPT-6.1 Sol High review/rechecks |No remaining P1 source/docs blocker | Reviewer independently passes9 contract-selection tests and1 selected-schema MCP test under exact1.30; verifies all4 retained fixture identities and cold dependency-free import/capabilities. |
| Whitespace, plan structure, local links and exact source scope |Final staged checks recorded in ledger | Structural evidence does not certify product training or future stages. |

The union is53 distinct agent cases,17 MCP protocol cases and9 approval cases;
all79 pass with zero skips. Local receipts and exact source fingerprints are
retained by the integration environment; committed-head CI separately verifies
the published source. Tests use actual domain authorization and process custody.

## Independent findings and corrections

1. Initial server selection code omitted `re`; the actual post-dispatch test
   exposed the request failure before admission. Added the import and reran;
   the completed test now proves one committed Run and one consumed grant.
2. Blanket headerless route refusal could break additive shared legacy routes.
   Preserve old dispatch and require the exact new ID at each new shared branch;
   test both an additive alias and wrong/missing variant selections.
3. Unknown operation fragments/bounds previously lacked full schema proof.
   All declarations now pass the existing Draft202012 validator and closed
   bounds/scope checks before unknown operations are ignored. References refuse.
4. Inherited MCP1.29 observations were not pinned1.30 qualification. Provisioned
   the exact private hash-locked environment and reran every acceptance path.
5. First wrapper matrix fixture lacked `edit` and was correctly refused403.
   Issued an actual owner-authorized editor credential; all4 peer combinations
   now pass without injecting or bypassing authentication.

No automatic mutation retry, telemetry activation, user training campaign,
Rheon/lab modification or deployment occurred. Existing observation tests
explicitly opt into their own disposable test store. P2–P6 product claims and
E2–E4 integration remain pending their actual implementations and validation.
