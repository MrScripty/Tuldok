# Execution ledger

## 2026-10-14: Discovery and plan admission

Preserved clean saved branch `work` at f2751c3; fetched origin/main and created
`feat/generic-neural-project-execution` at exact d856a984535a430909761ed13ce42eadd55b0710.
No AGENTS.md/applicable skills found. Read the adopted plan template and relevant
standards from Coding-Standards dcc56f26 (available clone HEAD188beda1).
Read-only lab clone HEAD e8a90bf inspected: train_cpu.py contains actual NumPy CNN
gradients and Adam; trajectory_model.py fits independent gains in closed form.
Existing external_recipe_v1 and captured_cpu_python_v1 suffice for the proposed
adapter contract; no schema alteration is admitted. Delegation authorizes start of
the scoped plan after structural validation. Publication/draft PR authorized;
merge/final tags are not part of this lane.

## 2026-10-14: Generic CLI qualification

Implemented `project_cli.py` exclusively through public AgentClient and
verify_artifact APIs. Explicit open/inspect/recipe/prepare/preflight/submit/status/
cancel/download commands share production owners; the CLI neither creates
grants nor retries mutations. Downloads verify whole SHA256 before exclusive
mode0600 publication and preserve existing/concurrently created work.

Recorded [generic verification](reports/verification.md). Final optional-environment
command `.venv-agent/bin/python -m unittest discover -s tests -p 'test_agent_*.py' -v`
ran30 tests in45.611s:29 passed,1 skipped because an actual classifier runtime was
not selected. This includes all7 new CLI tests plus actual SDK→HTTP→domain
qualification. The environment came from unchanged `requirements-agent.lock`
with required hashes; `pip check` passed. Other observed checks:28 external
tests,5 artifact-segment tests, unchanged actual Chromium external workflow,
controller/syntax/whitespace checks, structural plan validation and6 read-only
lab NumPy trainer checks. No neural pressure reproduction is inferred.

Moved the CLI tests to `test_agent_project_cli.py` so existing optional-agent CI
runs them without changing app dependencies or the workflow. Base environments
explicitly skip only its2 HTTP tests if JSON Schema is absent; those skips do not
count as CLI acceptance. No changes to other implementation owners.

The lab CNN's radius-one limitation and modal optimizer_steps0 are now documented
as distinct model-acceptance constraints. A1/A2/A4 generic acceptance is satisfied;
A3 and Milestone2 remain blocked pending paired lab sources/data and parent
coordination. No corresponding execution was denied or attempted with unknown
outcome. The original stale `work` branch and read-only lab source remain intact.
