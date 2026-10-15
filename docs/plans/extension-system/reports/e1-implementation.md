# E1 implementation and evidence

2026-10-15. Current user delegation explicitly authorizes E1–E4 implementation,
separate branches/draft PRs, relevant tests and independent review. Integration
lead thread `01a13f2b-3678-73df-8bce-2f57a04de00b` owns all merges and serial
shared-file integration. Source baseline is PR63 `f3f2d2b` and architecture
PR62 `f99182c`; latest fetched main `d788e08` merges both without production
P1–P6 implementations. No AGENTS.md or repository .agents skills are present in
this execution environment. Adopted Coding Standards source `dcc56f26` was read;
no live standards MCP certification is claimed.

## Result and ownership

E1 adds canonical data-only schema files, stdlib-only decoder/catalog with lazy
explicit optional validation, immutable project v2 references, and a real browser
catalog using existing components/styles. It preserves v1 shapes and legacy agent
discovery. The explicitly versioned owner-only project-snapshots HTTP projection
prevents legacy operations from silently accepting v2 before P1. No numerical
code enters the host, no new process supervisor/queue exists, and execution,
runtime qualification and extension permission remain unavailable.

Projects owns root handles/saved enablement; the extension contract owns schemas,
identity/bounds/static compatibility; Access still owns credentials. A fresh
manifest creates a new snapshot instead of mutating enablement. Source drift,
malformed siblings, unavailable definitions, exact dependency failures and conflicting
provider identities are separately represented. Schema content hashes are returned
so SDK consumers can use exact authority bytes later. No duplicate schema interpreter
or global plugin registry is introduced. The three schemas are authored canonical
JSON, not generated files requiring a second maintained generator.

Isolated write set: E1's extension contract/schemas/requirements, Projects,
workspace-projects UI, tests/fixtures/contracts and plan evidence. The minimal
`app.py` projection patch is supplied for lead serial integration. A new dedicated
`.github/workflows/extensions.yml` is a directly affected write-set addition:
it explicitly provisions the optional locked validator, runs real PostgreSQL,
HTTP, legacy/project and browser gates, and changes no existing gate/assertion.
Its full Git history fetch supports the pinned old-reader counterexample.
No `agent_api.py`, service or shared CSS edit is made.

The baseline workspace stylesheet explicitly selects light colors. This slice
reuses that owner and does not claim the planned compact dark theme is implemented;
that shared visual change stays with the lead's P3 integration. Current browser
geometry/keyboard/catalog claims below are proved at both required widths.

## Observed local evidence

Actual environment: Linux, Python 3.12.14, psycopg3.3.6, PostgreSQL17 in a
task-owned disposable Docker container, Node24.19.0 and Chromium. The app/HTTP
checks use an isolated environment explicitly provisioned from requirements.txt
and the optional hash-pinned extension validator closure. A second fresh Python
venv has **only** the validator closure, without app/DB/Torch provisioning.

- `python -m unittest discover -s tests -p test_extensions.py -v`: 15 tests pass
  in the fresh validator-only environment. Strict JSON/bounds, unknown format,
  nested unsupported keywords, namespace/content drift, missing validator,
  source inventory, malformed/missing siblings, conflicts independent of JSON
  key order and exact unavailable dependencies are covered. A fresh process
  verifies importing extension_contract does not import app/jsonschema/DB/Torch.
- `python -m unittest discover -s tests -p test_extension_http.py -v`: 9 tests
  pass against actual disposable PostgreSQL and ThreadingHTTPServer. Owner auth,
  agent denial, legacy refusal/no registration, unchanged v1/saved bytes,
  immutable enablement, missing/rebound/symlink roots, zero Run/grant publication,
  strict requests and current source drift are observed.
- The same HTTP suite executes the **pinned old Projects reader** against an
  actual saved v2 row and observes its silent legacy projection. It also makes a
  quiesced real pre-v2 backup, adds v2 to the subsequent original store, restores
  the backup into a newly created database and new destination, and checks exact
  original v1 project document bytes. This proves the selected operator rollback;
  it does not claim a DDL downgrade gate or full E4 extension-Run restoration.
- `python -m unittest discover -s tests -p test_projects.py -v`: 17 existing
  Projects tests pass, independently reproduced by the reviewer.
- Legacy compatibility: `test_agent_api.py` (17 tests) and
  `test_agent_project_cli.py` (7 tests) pass against their actual relevant HTTP/
  owner paths. These are existing contract/custody fixtures, not E2 qualification.
- `node tests/browser_workspace_extensions.cjs --scenario catalog`: actual
  `/workspaces` opens v2 via owner keyboard form, shows valid/malformed/missing
  packages and separate runtime/permission reasons, expands exact identities by
  keyboard, checks 1440/390 geometry, escapes an active-label trap, switches to
  disabled context, rejects a deliberately late old fetch and survives reload.
  Source snapshots are identical, execution markers absent, no Run/action submit
  and no external browser request occurs. Receipt/screenshots are in
  `build/qa/workspace-extensions-catalog/run-RmVjOM/` (dirty source development run).
- `node tests/browser_workspace_project.cjs`: existing v1 keyboard, project
  isolation, evidence text, 1440/390 geometry, reload/server restart and no
  execution checks pass; receipt `build/qa/workspace-project/run-wpRYAM/`.
- Python compilation, JavaScript syntax and `git diff --check` pass. Fresh
  `pip install --require-hashes -r requirements-extensions.lock` succeeds for the
  complete selected Python3.12/Linux validator closure. Startup never runs it.

Browser fixtures are authored static declarations/source execution traps.
They prove inspection/inertness, **not** model correctness, hardware/runtime
qualification, CPU training/inference, checkpoint publication, package download
or fresh inference. No fixture result substitutes for E2–E4 real acceptance.

## Independent review

Read-only reviewer `/root/e1_review`, explicitly GPT-6.1 Sol High, inspected the
canonical plan/standards and final source. It reproduced the contract/actual
HTTP/existing Projects checks (35 tests at its first closure) and independently
verified existing v2 GET denies an inspect/edit agent bearer with403.
Findings resolved in production code and regressions: preserve legacy operations
through explicit HTTP variant; make new routes owner-only before P1; remove
unsupported v2 legacy buttons; isolate actual missing definitions; avoid
JSON-key-order identity comparisons; classify nested unsupported keywords
consistently. No remaining actionable issue was reported at that closure.
Final independent recheck also passed the nine real HTTP/rollback tests,
workflow/docs, all fifteen contract tests and actual HTTP negatives for grown
source bytes and budget exhaustion. It found and verified a regression fix:
reserve failed reads using declared file size, so a small missing source cannot
starve an unrelated healthy package. No actionable finding remains.

## Integration and retained resources

E1 is implemented/locally verified; lead serial integration and exact-head CI are
required before acceptance. No merge is performed by this worker. Worktree
`/workspace/Tuldok-extension-e1` and `feat/extension-e1-manifest-catalog` stay
`retained-protected`: continuing purpose is lead review/integration and possible
stacked SDK preparation; next disposition belongs to the lead after integration
and after all dependent branches stop requiring it. Exact commit/PR is recorded
in the handoff. Main and other agents' work remain untouched.

P1 lead coordination is retained in
[PR63 handoff](https://github.com/MrScripty/Tuldok/pull/63#issuecomment-6198421362)
and the executor's following comments. Local cloud-thread messaging is unavailable;
no background monitor or proxy message channel is created.

E2 waits accepted P1–P3/P4 generic evidence and an actual qualified runtime. E3's
real A/B gate waits E2; only independent static authoring preparation can proceed.
E4 waits P5. Whole X1 and X2–X5 remain pending; only E1's discovery portion of X1
has the observed evidence listed above.
