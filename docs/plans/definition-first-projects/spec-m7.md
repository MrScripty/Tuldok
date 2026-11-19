# Implementation spec: milestone 7, the app and the agent interface

This continues the earlier specs in this folder. Section 1 of [spec-m1-m2.md](spec-m1-m2.md) (rules for implementers) applies, with the two exceptions in section 1 below. This is the first milestone that changes existing Tuldok files: `app.py`, `agent_api.py` and `mcp_stdio.py`, each by a small, additive block.

**Done when:** Tuldok started with `--project-folder examples/tiny-project/project` serves the project; an agent holding only an agent credential reads the project, asks for the plan, requests a build of `benchmarks/held-out`, the owner approves that request, the agent watches the training's progress and reads the results and the chart, all through the agent interface; and the catalog and old project capability manifests are byte for byte what they were before this milestone.

## 1. Decisions

- **One folder per Tuldok process.** `python app.py --project-folder PATH` serves that folder and nothing else. It cannot be combined with `--project-root`, `--project-files-root`, `--project-runtime-source`, `--project-transfer-control` or `--project-transfer-root`. `--data` still names the catalog directory, which holds the credentials.
- **Every operation opens the project for a moment**, as the commands do (`builds.opened`), so files changed on disk are imported before the operation answers and the command line keeps working beside a running app. Nothing holds the project open between operations.
- **Every operation is `POST /api/project/<name>` with a JSON object body**, where `<name>` is the operation's name after `project.`. There are no path or query arguments, so a reference such as `recipes/small-net-a` needs no escaping. Every request must select its contract with the `Tuldok-Operation-Contract` header, as every operation added since the first agent release does.
- **A build asked for through the interface is a build request.** The owner's own request starts by itself. An agent's request waits until the owner approves it, and the approval covers exactly what was shown: section 4. This keeps the plan's rule that nothing runs without the owner's approval. `access.py` already refuses the `execute` scope to agents, so the request path is separate from it.
- **The app runs approved requests one at a time** in one worker thread, with `builds.execute`. A foreground `build` from the command line is unchanged and makes no request.
- **Exceptions to the import rule.** `tuldok_project/host.py` (new) is the one module of the package that imports the app's kept layers: `metadata`, `access` and `agent_api`. `agent_api.py` imports `tuldok_project.operations`, which imports only the standard library. No other module of the package imports from outside it, and nothing imports the old `project_*.py` modules.
- **Not in this milestone:** see section 9.
- **As built:** section 12 lists where the code differs from the sections below. Where they differ, section 12 is right.

## 2. Operations

Profile `project_folder`. Each row is one operation `project.<name>`. **Who** is the rule for the caller:

| Who | Rule | `access.require` call in the host |
| --- | --- | --- |
| inspect | any credential with `inspect` | `require('inspect', name)` |
| edit | any credential with `edit` | `require('edit', name)` |
| cancel | any credential with `cancel` | `require('cancel', name)` |
| request | the owner, or an agent whose credential includes `execute` | `require('inspect', name)`, then the scope list of `identity()` must contain `execute` |
| owner | the owner only | `require('approve-execution', name, owner_only=True)` |

Arguments marked `?` are optional. A reference is text of 1 to 200 characters. A run or a build request is named by its id or by at least its first 6 characters. Unknown arguments are refused.

| Name | Who | Arguments | Result (top-level keys) |
| --- | --- | --- | --- |
| `summary` | inspect | none | `project_id`, `name`, `folder`, `code_root`, `kinds`, `states` (`Project.summary()`), and `worker`: `running`, `elsewhere` or `stopped` (section 4) |
| `status` | inspect | none | the keys of `Project.status()` |
| `check` | inspect | none | `ok`, `errors`, `warnings` (counts), `problems` (the first 200, each `severity`, `path`, `pointer`, `message`). Reads the folder on disk with `check.check_folder`; does not open the project, so it answers when the folder has errors |
| `definitions` | inspect | `kind?` | `definitions` (`Project.definitions`) |
| `definition` | inspect | `reference` | the keys of `Project.definition` |
| `graph` | inspect | none | `nodes`, `edges` |
| `results_overview` | inspect | none | `benchmarks` (`Project.results_overview()`) |
| `results` | inspect | `benchmark`, `subject?`, `metric?`, `group?`, `offset?` (0), `limit?` (500, at most 2000) | `rows`, `total` |
| `values` | inspect | `benchmark`, `subject`, `metric?`, `offset?` (0), `limit?` (200, at most 1000) | `rows`, `total` |
| `chart` | inspect | `chart`, `svg?` (false), `theme?` (`light` or `dark`) | `data` (`charts.chart_data`), and `svg` (text) when asked |
| `report` | inspect | `theme?` | `html` |
| `plan` | inspect | `targets` (0 to 50 references), `every?` (false) | the keys of `plan.build_plan` |
| `estimates` | inspect | none | `estimates` (`builds.stored_estimates`) |
| `environments` | inspect | none | `environments` (`environments.listing`) |
| `environment` | inspect | `reference` | the keys of `environments.show` |
| `runs` | inspect | `reference?`, `limit?` (100, at most 500) | `runs`, newest first |
| `run` | inspect | `run` | the run's row, `product`, `builder_alive`. The row's `env` is replaced by `env_names`, the sorted names of its variables: values are never sent |
| `progress` | inspect | `run`, `stdout_offset?`, `stderr_offset?` | `run` (`builds.run_summary`), `event`, `stdout`, `stderr` (each `text`, `offset`, `size`, `skipped`, from `builds.read_log`), `ended`. Without an offset the last part of the log is read |
| `products` | inspect | `reference?` | `products` |
| `build_requests` | inspect | `state?`, `limit?` (100, at most 500) | `requests`, newest first, without their `covers` |
| `build_request` | inspect | `request` | the request (section 4) with `covers`, and `runs`: the runs of its plan |
| `activity` | inspect | `offset?` (0), `limit?` (100, at most 500) | `items`, newest first, `total` |
| `set_definition` | edit | `reference`, `text` | as `definition` |
| `remove_definition` | edit | `reference` | `removed` (the reference) |
| `save` | edit | none | the keys `Project.save()` returns |
| `resolve_conflict` | edit | `choice` (`keep` or `discard`) | as `summary`. Opens the project with that `on_conflict` choice |
| `import_values` | edit | `text` | `benchmark`, `subject`, `values` (count). A request is at most 1 MiB, so larger values files are imported by the command line or published by the run that made them |
| `check_environment` | edit | `reference` | as `environment` |
| `connect_environment` | owner | `reference`, `interpreter` | as `environment` |
| `disconnect_environment` | owner | `reference` | `disconnected` (the reference) |
| `request_build` | request | `targets` (0 to 50 references), `every?` (false), `scratch?` (false) | the request |
| `approve_build` | owner | `request` | the request |
| `decline_build` | owner | `request`, `reason?` (at most 400 characters) | the request |
| `cancel_build` | cancel | `request` | the request |
| `cancel_run` | cancel | `run` | the keys of `builds.cancel` |
| `stop_run` | cancel | `run` | the keys of `builds.stop` |

**Results are plain JSON.** Times are ISO 8601 text in UTC. A number that is not finite is `null`. A result is an object; the keys listed are always present and others may be.

**Refusals.** A `ProjectError` becomes `{"error", "code"}` plus, when not empty, `problems` (the first 50, as in `check`), `references` and `files`. The HTTP status is 404 for `not-found`, 400 for `invalid`, 403 for `forbidden`, and 409 for every other code. Codes added by this milestone: `forbidden` (the service's own check of the actor), `nothing-to-build`, `too-many`, `not-awaiting`, `stale`, `not-cancellable`, `unavailable`.

## 3. The service

`tuldok_project/operations.py` holds the table above as data: a tuple `OPERATIONS` of frozen `Operation(name, summary, who, mutation, arguments, result)` records, where `arguments` is a JSON Schema object (closed: `additionalProperties` false) and `result` is the tuple of required result keys. `summary` is one plain sentence, shown to agents as the tool's description. `by_name(name)` returns one. `error_status(code)` gives the HTTP status. It imports only the standard library.

`tuldok_project/service.py`:

```python
class Service:
    def __init__(self, folder, *, dsn=None)     # opens the folder once and closes it; raises ProjectError
    def start(self)                             # starts the worker of section 4
    def close(self)                             # section 4; safe to call twice
    def call(self, name, arguments, actor)      # returns the result object or raises ProjectError
```

- `actor` is `{"actor_id", "kind", "label", "scopes"}`; `kind` is `owner` or `agent`.
- `call` checks, in this order: the operation exists (`not-found`); the actor satisfies its **who** rule from `kind` and `scopes` alone (`forbidden`); the arguments match its schema (`invalid`, with one problem per schema error). It then runs the operation and makes the result JSON-plain.
- Requests are answered one at a time: `call` holds one lock of the service while the project is open, so two requests never wait on each other through the database lock. The worker does not take that lock.
- Every mutating operation writes one row of `activity` (section 5), whether it was done or refused after the actor check.
- The service knows nothing of HTTP, `access` or `agent_api`.

## 4. Build requests

New module `tuldok_project/build_requests.py`, and one table in each project schema, created like the others:

```sql
CREATE TABLE build_requests (
  id text PRIMARY KEY,
  state text NOT NULL,
  targets jsonb NOT NULL, every boolean NOT NULL, scratch boolean NOT NULL,
  covers jsonb NOT NULL, covers_sha256 text NOT NULL,
  requested_at timestamptz NOT NULL, requested_by jsonb NOT NULL,
  decided_at timestamptz, decided_by jsonb,
  started_at timestamptz, finished_at timestamptz,
  owner_pid integer, owner_boot text,
  plan_id text, cancel_requested boolean NOT NULL DEFAULT false,
  result jsonb, problem text);
```

`requested_by` and `decided_by` are `{"actor_id", "kind", "label"}`. A request as returned has every column except `owner_pid`, `owner_boot` and `covers_sha256` kept as they are, with `covers` left out of lists.

**States:** `awaiting-approval`, `queued`, `running`, `succeeded`, `failed`, `cancelled`, `declined`, `expired`.

**What a request covers.** `covers` is computed from the plan (`plan.build_plan`) and the code root:

```json
{"targets": [...], "every": false, "scratch": false,
 "commit": "<HEAD of the code root, or null when scratch or not in Git>",
 "steps": [{"reference": "...", "subjects": [...]}],
 "definitions": {"<reference>": "<SHA-256 of its text>"}}
```

`steps` are the plan's steps whose action is `build`, in plan order, with the benchmark subjects that would run (an empty list for other kinds). `definitions` has every reference that appears in the plan's steps, whatever its action. `covers_sha256` is the SHA-256 of `covers` as JSON with sorted keys and no spaces.

**Requesting.** The plan is made. A plan with blocked targets is refused (`blocked`, as `execute` does), and a plan with nothing to build is refused (`nothing-to-build`). At most 20 requests may be awaiting approval or queued (`too-many`). The owner's request is stored `queued` with `decided_by` the owner. An agent's is stored `awaiting-approval`.

**Approving.** Only an `awaiting-approval` request (`not-awaiting`). `covers` is computed again now; if its SHA-256 differs, the request becomes `declined` with a problem naming what changed (the commit, or up to five references), and the call is refused with `stale`. Otherwise the request becomes `queued`. **Declining** makes it `declined` with the reason as its problem.

**The worker.** One thread per service, started by `start()`. It first takes `<local home>/<project id>/build-requests.lock` with a non-blocking `flock`; if another process holds it, this service runs no requests and `summary` reports `worker: "elsewhere"`. Then, about once a second, with the project open only for the database steps:

1. Mark as `failed` every `running` request whose owner process is gone (`builds.boot_id`, the pid), with the problem "Tuldok stopped while this was running."
2. Take the oldest `queued` request. If it was decided more than 3600 seconds ago it becomes `expired`. If its `covers`, computed again, has another SHA-256, it becomes `failed` with the problem naming what changed. Otherwise it becomes `running`, with this process recorded.
3. Run `builds.execute(folder, plan, confirm=<always true>, scratch=..., dsn=..., expect=covers, stop=...)` with the project closed.
4. Record the outcome: `succeeded` when `ok`; `cancelled` when cancel was requested; otherwise `failed` with the problem of the step that did not succeed, or the message of the `ProjectError` that `execute` raised. `plan_id` and `result` (the steps as `execute` returned them) are stored.

An exception in the worker other than `ProjectError` marks the request `failed` with its type and message, and the worker goes on.

**Two additions to `builds.execute`**, both keyword arguments that default to `None` and change nothing when absent:

- `expect`: a `covers` object. After the code is prepared, a commit that is not `expect["commit"]` (when that is not null) refuses the build with `stale` before anything runs. Before each step is run, every definition the build reads to run it (the step's own, its environment, the step definition it runs with, a benchmark subject's recipe) must have the text whose SHA-256 is in `expect["definitions"]`; otherwise the build stops there with `ProjectError` `stale`, naming the reference. Steps already finished stay as they are.
- `stop`: a function called before each step; when it returns true the build ends there with `ok` false.

**Cancelling a request.** `awaiting-approval` or `queued` becomes `cancelled`. `running` gets `cancel_requested` set and each active run of its plan is asked to stop with `builds.cancel`; the worker's `stop` function reads the flag. Any other state is refused (`not-cancellable`).

**Closing.** `Service.close()` requests the cancellation of a running request, waits for the worker up to 30 seconds, and returns. The custodian of a run already stops its run when the process that started it dies.

`summary`'s `worker` is `running` while this service's worker holds the lock, `elsewhere` when another process does, and `stopped` before `start()` and after `close()`.

## 5. Activity

```sql
CREATE TABLE activity (
  id bigserial PRIMARY KEY, at timestamptz NOT NULL,
  actor jsonb NOT NULL, operation text NOT NULL,
  target text NOT NULL, outcome text NOT NULL, detail text NOT NULL);
```

One row for each mutating operation that passed the actor check: `target` is the reference, run or request it named (or empty), `outcome` is `done` or the refusal's code, `detail` is empty or the first 400 characters of the refusal. `approve` and `decline` from the command line (section 8) write a row with the actor `{"actor_id": null, "kind": "owner", "label": "command line"}`. Reads are not recorded.

## 6. The app

**`tuldok_project/host.py`:**

```python
class ProjectHost:
    project_folder_mode = True
    def __init__(self, data_path, folder, *, dsn=None)   # Metadata, Access, Service; starts the worker
    def capabilities(self)                               # agent_api.capabilities(catalog id, profile='project_folder')
    def dispatch(self, name, arguments)                  # -> (status, result)
    def close(self)
```

It has `db`, `lock` and `access` as `Dataset` and the old project mode have, because `app.py`'s handler uses them for sign-in and credentials. `dispatch` makes the `access.require` call of section 2 inside the caller's bound credential, builds `actor` from `access.identity()`, calls the service, and turns a `ProjectError` into `(status, body)` as section 2 says. Access errors are not caught: `app.py` already answers them.

**`app.py`,** the smallest change that does this, with no restructuring of what is there:

| Request | Folder mode | Other modes |
| --- | --- | --- |
| start-up | `--project-folder PATH` builds a `ProjectHost`; a folder that does not open ends start-up with the message and its first problems | unchanged |
| `POST /api/project/<name>` | the body is read as strict JSON with the agent request limit; `agent_api.require_selection` for `project.<name>`; reply with `dispatch`'s status and result | 409 `unavailable`, "Start Tuldok with --project-folder to use this." |
| `GET /api/agent/capabilities` | `host.capabilities()` | unchanged |
| `GET /api/workspace/context` | `{"version": 1, "mode": "real", "dataset_id": ..., "project_folder": true}` | unchanged |
| `/api/access/...` | unchanged | unchanged |
| any other `/api/` route | 409 `unavailable` | unchanged |
| `GET /`, `/workspaces`, `/workbench` | the page below | unchanged |

**The page.** `static/project-folder.html`, `static/project-folder.js` and `static/project-folder.css`: the existing sign-in bar (`auth.js`, `auth.css`), the project's name and folder, a Reload button, and the report (`project.report`, in the theme the browser prefers) shown in an `<iframe sandbox>` through `srcdoc`. It reads the contract versions and hashes it needs from `/api/agent/capabilities`; nothing is pinned in the script. It is a stand-in until the workspace screens have their own plan, so it has no editing, no approval buttons and no other view.

## 7. `agent_api.py` and `mcp_stdio.py`

- Before `_LOOKUP` is built, each row of `operations.OPERATIONS` is registered: method `POST`, path `/api/project/<name>`, the row's argument schema, `mutation` from the row, the row's `summary` as the description. Its output schema is the usual pair: status 200 to 299 with a result object that requires the row's result keys and allows others, or status 400 to 599 with `{"error" (required), "code", "problems", "references", "files"}`.
- The owner rows are added to `_OWNER_OPERATION_IDS`. Retry is `read` for a row that is not a mutation and `never` for one that is, which is what `contract()` already answers.
- `capabilities(catalog_id, profile)` accepts `project_folder`: that profile has the `project.*` operations, `context.get` and `identity.get`, all `available`. The `catalog` and `project` profiles never include a `project.*` operation.
- `ProjectFolderOwnerClient(AgentClient)`: bootstraps as the owner and offers the `project.*` operations, in the way `PublicationOwnerClient` does. The plain `AgentClient` needs no change to work as an agent in folder mode.
- `mcp_stdio.py` gains `--project-folder-owner`, selecting that client, in the existing mutually exclusive group.

**Nothing published may change.** These must be exactly what they were before this milestone, and one new test asserts the three digests:

| What | SHA-256 of `agent_api.encoded(...)` |
| --- | --- |
| `capabilities('b' * 32, profile='catalog')`, 115 operations | `b31b7a2b794020622e64d593cd29455226a4170451f15201e28cad5d9edd18f1` |
| `capabilities('b' * 32, profile='project')`, 152 operations | `58e4270277a38b58869ca4c6ae4bccffe74387b2ee70d3c178b30821f8d27320` |
| `discovery()` | `9c02284ed750bce31c53100d4657deaf40b519c9d17d5e3165b6b6342930b660` |

The pinned contract fixtures under `tests/fixtures/` are not regenerated: they record earlier contracts, and this milestone only adds.

## 8. Command line

| Command | Does |
| --- | --- |
| `requests FOLDER [--json]` | lists the build requests, newest first |
| `approve FOLDER REQUEST` | approves a request, showing what it covers and asking for confirmation unless `--yes` |
| `decline FOLDER REQUEST [--reason TEXT]` | declines it |

A request approved from the command line is run by the app that serves the folder, when one is running; the approval expires after an hour like any other.

## 9. Not in this milestone

- **Installing an environment** (`set-up`) and **measuring estimates** (`estimate`) stay command-line actions. Both run for a long time with the project held open, so serving them needs the same background handling a build has.
- **Variables passed to a build** (`build --env`) are not offered by the interface.
- **Rebinding a project to another folder** and **forgetting a project** stay command-line actions.
- **The catalog queue does not take the GPU lock.** Builds of the new core, from the app or the command line, wait for each other on `gpu.lock`. A GPU run started by a Tuldok process in catalog mode does not. The earlier note that the two would share one capacity object assumed one process serving both; the modes are separate processes.
- **Screens.** The page is the report only.

## 10. Slices

| Slice | Files | Notes |
| --- | --- | --- |
| T13 service | `tuldok_project/operations.py`, `tuldok_project/service.py`, the `activity` table, `tests/test_tuldok_project_service.py` | every operation except the six of section 4 that act on a request (`request_build`, `approve_build`, `decline_build`, `cancel_build`, `build_requests`, `build_request`), which it declares in the table and passes to `build_requests` functions with these names: `request`, `approve`, `decline`, `cancel`, `listing`, `show`, each taking `(project, ...)`; until T14 they may raise `unavailable` |
| T14 build requests | `tuldok_project/build_requests.py`, the worker in `service.py`, `expect` and `stop` in `builds.py`, the three commands in `__main__.py`, `tests/test_tuldok_project_build_requests.py` | after T13; stand-in commands only, from the `buildable` fixture |
| T15 app | `tuldok_project/host.py`, the blocks in `app.py`, `agent_api.py`, `mcp_stdio.py`, the page, `tests/test_tuldok_project_http.py`, and a "Serving a project" section in `docs/contracts/project-folder.md` | after T13, beside T14 |

Existing tests that must still pass (173 tests, 31 skipped, about six and a half minutes before this milestone), run from the repository root with `TULDOK_DATABASE_URL` set as `PYTHONPATH=tests .venv/bin/python -m unittest <names>`: `test_agent_api`, `test_agent_negotiation`, `test_agent_http`, `test_mcp_stdio`, `test_agent_project_snapshots`, `test_retained_analysis_contracts`, `test_run_artifact_segments`, `test_run_phase_timings`, `test_run_publication_http`, `test_project_measurements_clients`, `test_project_files_clients`, `test_project_files_owner_mcp`, `test_agent_domain_parity`, `test_agent_workflow`.

## 11. Acceptance run

Done by the orchestrating session, with a throwaway catalog and database, the owner's two existing environments connected, and the same tiny training as milestone 6. An agent that is given only an agent credential and the Python client (`agent_api.AgentClient`) reads the summary, asks for the plan of `benchmarks/held-out`, requests the build, waits for the owner's approval, follows the training's progress, and reads the ranking chart. The owner's side is one `approve`. Afterwards: a second request is refused with `nothing-to-build`, no process of the build is left, and the example is unchanged in Git.

## 12. As built

Found while implementing; the code and its tests follow this section.

- **36 operations.** Section 2's table has 36 rows.
- **The published scopes** of a contract are `inspect` for inspect, `inspect` and `edit` for edit, `inspect` and `cancel` for cancel, `inspect` and `execute` for request, and `inspect` and `approve-execution` for owner. The service's own actor check requires the same scopes, the owner included.
- **`AgentClient` did need one change.** It accepted only refusal codes without hyphens, so every refusal of the new core (`not-found`, `nothing-to-build`) reached an agent as a transport error. For a `project.*` selection it now accepts a code with hyphens and keeps `problems`, `references` and `files`. No existing line changed.
- **An unknown `project.*` name** is refused 409 `contract_mismatch` by the contract selection, before the service is reached. Arguments are checked by the service, which answers 400 `invalid` with one problem per schema error; `agent_api.validate_selected`, which would answer without problems, is not called for these routes.
- **Other routes in folder mode.** A route that has a contract and is sent without its header is refused 409 `contract_mismatch` before the folder-mode refusal 409 `unavailable` is reached.
- **An exception that is not a refusal** is answered 500 with code `internal` and the exception's type, and written to `activity` with the outcome `error`.
- **`expect` checks** the step's own definition, its environment and a benchmark subject's recipe. No field of the format names a separate step definition.
- **`plan_id` of a running request** is recorded when its first run starts, so that cancelling can find its runs. A cancel that arrives earlier is honoured when the first run starts.
- **The covered subjects** of a benchmark step are those `execute` would run: the plan's, less the ones already built.
- **The worker** first asks, on a connection of its own, whether any request is queued or running, and opens the project only then. A service that finds the worker lock taken tries again every pass. Between requests, a `running` request of its own process counts as orphaned. A pass that fails is logged once while the failure repeats, and the request stays queued.
- **`activity`** has its own module, `tuldok_project/activity.py`, and its rows are written on a connection of their own, so a refusal is recorded when the project does not open.
- **Bare names.** `results`, `values` and `chart` take a bare name or a reference, as the commands do.
- **`requests`** on the command line is a read and writes no activity row.
