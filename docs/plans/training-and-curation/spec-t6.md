# Implementation spec: serving a trained model

This is phase 6 of [the training and curation plan](plan.md). It follows that plan's rule: Tuldok supplies a contract (the `serve` declaration and the protocol), the orchestration (start, approval, supervision, stop) and the views; the project writes its own Python. Tuldok's server never imports the project's code: the entry point runs in a separate process, in the recipe's environment, as a build's command does ([spec-m6.md](../definition-first-projects/spec-m6.md) section 4). Who may do what follows [spec-w3.md](../definition-first-projects/spec-w3.md) and `service._allowed`; credentials and sessions are those of [actors.md](../../contracts/actors.md). The page follows [spec-w4.md](../definition-first-projects/spec-w4.md): what changes on its own (a model becoming ready) is set in place, nothing is rebuilt by a timer. Decision 4 of the plan holds: **a served model is reachable only from this machine**; Tuldok opens no new listener, and the endpoint is a route of the server Tuldok already runs on the loopback address.

**Owner, 2026-11-19:** "We should also have serving trained models as a REST endpoint and autologging."

**After this phase** a recipe may declare `serve`: the file and functions of the project's own entry point. The owner starts serving a built model from the Train tab or from the model's drawer (an agent asks, and the owner approves, as with a build); Tuldok starts the entry point in the recipe's environment with the model's product, waits for it to load, and answers `POST /api/serve/<model>/predict` behind Tuldok's credentials. Every request's time is logged; a session's timings can be written into a benchmark as per-case values, so the model as served is a benchmark subject like any other. A served model stops when asked, after an idle time, or when Tuldok stops.

## 1. The declaration

A recipe may have a `serve` object:

| Field | Required | Rule |
| --- | --- | --- |
| `module_file` | yes | a code path (as `settings_file`) of a `.py` file: the project's entry point |
| `function` | no | a Python name (`^[A-Za-z_][A-Za-z0-9_]{0,63}$`), default `predict`: called for every request as `function(model, inputs)` |
| `load` | no | a Python name: called once at start as `load(product)` with the product directory; what it returns is `model`. Without `load`, `model` is the product directory (a string) |
| `environment` | no | a reference to `environments/`; default the recipe's `run.environment`. One of the two is required |
| `idle_minutes` | no | integer 1 to 1,440: stop after this long without a request; default the machine's (section 4) |
| `start_seconds` | no | number 1 to 3,600, default 120: how long `load` may take before the start fails |
| `request_seconds` | no | number 0.1 to 600, default 60: how long one request may take before the process is stopped as failed |
| `gpu` | no | boolean, default false: without it `CUDA_VISIBLE_DEVICES` is empty, as for a run |
| `example` | no | an object: the inputs the page's "Try it" starts with |

`check` adds: `module_file` is a code path that must exist (an error; a warning for earlier work, as other code paths), and ends in `.py`; no environment in `serve` or in `run` is an error. `serve` is not an input: it never makes a model out of date, and building never reads it.

Example:

```json
"serve": {"module_file": "serve.py", "load": "load", "function": "predict",
          "idle_minutes": 20, "example": {"x": [1, 2, 3]}}
```

and the project's `serve.py`:

```python
import json, os

def load(product):
    with open(os.path.join(product, 'weights.json')) as handle:
        return json.load(handle)

def predict(model, inputs):
    return {'y': [model['constant'] + value for value in inputs['x']]}
```

**Why a module and two functions, not a command that speaks a protocol.** Both run the project's code in its own process. With a command, every project writes the read loop, the framing, the bounds and the array encoding itself, and one stray `print` in the model's code (or a library's warning on standard output) corrupts the protocol. With a module, Tuldok's small adapter (section 2) owns all of that once, in the standard library: it moves the process's standard output to the log before importing the project's file, speaks the protocol on two private pipes, and decodes and encodes arrays. The project writes two plain functions it can also call from a test or a notebook. It is the simpler contract for projects and the one Tuldok can make safe. A project that needs a server of its own can still write one as a `run` and is outside this phase.

There is no `tuldok_log` helper for this: the two functions above are the whole skeleton, and the contract document carries the example.

## 2. The process and the protocol

**Starting.** The model is the recipe; serving needs its current product (refused `not-built` without one) and the environment's recorded interpreter, checked as a build checks it (refused `not-ready`). The code is a snapshot as for a build (`snapshot.prepare`): the committed code at HEAD, refused `dirty` when tracked files under the code paths have changes, unless the start asks for `scratch` (the code root as it is on disk). The session records the commit, the product's run, the environment and the interpreter.

Tuldok starts, in the code directory, `<interpreter> -I <Tuldok>/tuldok_project/serve_adapter.py` with the two pipe descriptors, the module file, the function names and the product directory as arguments. `-I` keeps Tuldok's own directory and `PYTHON*` variables out of the process; the adapter puts the code directory first on `sys.path`. The environment is a run's (`PATH`, `HOME`, `USER`, `LOGNAME`, `LANG`, `LC_ALL`, `TZ`), `CUDA_VISIBLE_DEVICES` empty unless `gpu`, `TULDOK_PRODUCT` (the product directory), `TULDOK_SERVE_MODEL` (the recipe) and `TULDOK_RUN_ID=serve-<session>`. Standard input is empty; standard output and standard error go to one log. The process is started in a session of its own with `PR_SET_PDEATHSIG` (it dies with Tuldok), from a thread that lives as long as the process (the signal follows the thread that started it).

**The protocol,** one UTF-8 JSON object per line on the two private pipes:

1. The adapter imports the module, calls `load`, and writes `{"ready": true, "load_seconds": s, "numpy": bool, "python": "3.12.3"}`, or `{"ready": false, "error": "<the exception, one line>"}` and exits. No line within `start_seconds`: the start fails and the process is stopped.
2. Per request Tuldok writes `{"id": n, "inputs": {…}}`; the adapter calls `function(model, inputs)` and writes `{"id": n, "ok": true, "outputs": …, "model_seconds": s}` or `{"id": n, "ok": false, "error": "…", "model_seconds": s}` (the model raised: the session stays ready). No answer within `request_seconds`, an answer longer than 16 MiB, one that is not JSON or has another id, or the process gone: the session fails and the process is stopped.
3. When Tuldok closes the request pipe the adapter exits.

**Arrays.** A value in the inputs or outputs that is an object of exactly the keys `array` (`"float32"`), `shape` (0 to 8 integers ≥ 0) and `base64` (the little-endian float32 values in C order, standard base64, length exactly 4 × the product of the shape) is an array. The adapter gives `predict` such an input as a `numpy.ndarray` of float32 when NumPy is importable in the environment, otherwise as nested lists of floats. Nested lists of numbers are passed as they are. In the outputs, a NumPy array (anything with `shape`, `dtype` and `tobytes`) is cast to float32 and encoded so; a NumPy scalar becomes a number; tuples become lists; anything else that is not JSON is the request's error. Only float32 is encoded; other values are JSON numbers.

**Bounds.** A request body is at most 8 MiB (1 MiB through the operation, which is the operation contract's bound), JSON nested at most 64 deep, an array at most 2²⁴ elements; an answer at most 16 MiB. At most 8 requests wait for a served model; the ninth is refused `busy`. One request is in the process at a time.

**Stopping.** The request pipe is closed, the process group gets `SIGTERM`, then `SIGKILL` after 5 seconds, and every process carrying the session's `TULDOK_RUN_ID` is swept (`launcher.stop_strays`). The log keeps the first 4 MiB of output and then only says that more was dropped; the last 4 KiB are kept in memory as the tail shown with a failure.

## 3. The endpoint and who may use it

`POST /api/serve/<name>/predict`, where `<name>` is the recipe's name (`recipes/<name>`), on the server Tuldok already runs (`127.0.0.1` by default). The body is `application/json`, `{"inputs": {…}}` and nothing else. The credential is Tuldok's: a bearer credential, or the page's session cookie with a same-origin request, exactly as for `/api/project/<operation>`; no operation contract header is needed, so that any HTTP client can call it. It is answered only in project-folder mode.

| Answer | When |
| --- | --- |
| 200 `{"model", "session", "outputs", "timing": {"queue_ms", "model_ms", "total_ms"}}` | answered |
| 400 `invalid` | not a JSON object of `inputs` only, a malformed array, too deep |
| 401, 403 | no credential, or one without `inspect` |
| 404 `not-served` | the model is not being served |
| 409 `not-ready` | it is starting or awaiting approval |
| 413 `too-large` | the body is over 8 MiB |
| 422 `predict-failed` | the project's function raised; `error` says what |
| 502 `serve-failed` | the process broke the protocol or died; the session is failed |
| 503 `busy` | eight requests are waiting already |
| 504 `timed-out` | no answer within `request_seconds`; the session is failed |

**Who.** Calling `predict` needs `inspect`: it changes nothing kept, and the owner's start is the consent to run the code; least privilege lets an owner hand a client a credential that can only read and predict. Starting needs `request`, as a build: the owner's start runs at once, an agent's (with `execute`) waits for the owner's approval for up to an hour. Approving is the owner's. Stopping needs `cancel` (an agent with `cancel` may stop what it asked for or anything served, as it may cancel a build); stopping one that awaits approval declines it. Writing a session's timings into a benchmark needs `edit` (it imports values, as `import_values`).

## 4. Sessions, limits and the log

A **session** is one start of one model: `id` (32 hex), `model` (recipe reference), `state` (`awaiting-approval`, `starting`, `ready`, `failed`, `stopped`, `declined`, `expired`), `reason` (why it ended: `asked`, `idle`, `closing`, or the problem), who asked and decided, the times, the commit, scratch, the product's run and directory, the environment and interpreter, the pid, the idle minutes, the request counts, the last request's time and the output's tail.

**Limits of the machine,** two optional fields of the settings file (`local.py`): `serve_most`, how many models may be starting or ready at once (1 to 16, default 2), and `serve_idle_minutes` (1 to 1,440, default 30), the idle time of a model whose `serve` names none. A start (or an approval) past `serve_most` is refused `limit`, naming the ones served. A model already awaiting approval, starting or ready is refused `already-served`.

**The log,** under the project's local home, `serving/<session>/`: `session.json` (the session, written again at each change), `output.log` (section 2), and `requests.jsonl`, one line per request answered or refused after it reached the model: `{"n", "at", "ok", "status", "queue_ms", "model_ms", "total_ms", "bytes_in", "bytes_out", "error"?}` — the time waiting for the model, the model's own time (reported by the adapter around `function`), and the total from when Tuldok had read the request to when the answer was ready. At most 100,000 lines a session; past that requests are counted and not written. Sessions are in memory while Tuldok runs; `served` also lists the 50 newest sessions on disk, and a session left starting or ready by a Tuldok that is gone is shown `stopped` with the reason `Tuldok stopped`.

**Timing summary** of a session (`serve_session`): the count, how many failed, the span from first to last request, the throughput (answered requests per second over that span, null under two requests), and for `queue_ms`, `model_ms` and `total_ms` the mean, p50, p95, p99 and max of the answered requests (percentiles by the linear interpolation of `results.summarise`).

## 5. The model as served, as a benchmark subject

`serve_values` turns a session's answered requests into a [values file](../../contracts/project-folder.md#values-files) and imports it, as `import_values` does: `benchmark` and `subject` name a subject of that benchmark (whose `recipe`, when it has one, must be the served model); `metrics` maps metric ids of the benchmark to one of `total_ms`, `model_ms`, `queue_ms`, `total_s`, `model_s`, `queue_s` (default: each metric whose id is one of those names). Each answered request is a case `request-000001`, …; a request the model failed is a value `null` with its error as the reason. The commit is the session's, `produced` the time of its last request. The file is also written to the session's directory. The benchmark then holds per-case values, its summary rows (median, p10, p90, …), the intervals of spec-t3 and its charts; p95, p99 and throughput, which the results format has no column for, stay in the session summary.

How to use it: a benchmark of its own for serving, say `benchmarks/served-latency` with metrics `total_ms`, `model_ms` and `queue_ms` (`better: lower`, `units: ms`) and a subject per served model naming its recipe. Its `run` may be the project's own load script that calls the endpoint (built like any benchmark, writing its values), or it may be marked `earlier_work: {"rebuild": "no", …}` when its values come only from `serve_values`. The timings depend on what else ran on the machine; the session records when.

## 6. Operations

Seven rows of the `project_folder` profile, absent from `catalog` (its digest unchanged):

| Operation | Who | Mutation | Arguments | Result |
| --- | --- | --- | --- | --- |
| `served` | inspect | no | — | `sessions` (newest first), `servable` (each recipe declaring `serve`: `model`, `title`, `module_file`, `environment`, `built`, `product_run`, `example`, `session`), `most`, `idle_minutes` |
| `serve_session` | inspect | no | `session` | the session, `summary` (section 4), `recent` (the 20 newest request lines) |
| `serve_start` | request | yes | `model`, `scratch` | the session |
| `serve_approve` | owner | yes | `session` | the session |
| `serve_stop` | cancel | yes | `session` | the session |
| `serve_predict` | inspect | no | `model`, `inputs` | `model`, `session`, `outputs`, `timing` |
| `serve_values` | edit | yes | `session`, `benchmark`, `subject`, `metrics` | `benchmark`, `subject`, `values`, `file` |

They are answered outside the service's lock; those that read the project take it only for that. `serve_predict` never takes it. Refusals carry the codes of section 3 (`not-served`, `not-ready`, `busy`, …) with the statuses there.

## 7. The page

- **Train: Served models,** after Build requests: one row per recipe that declares `serve`, with its state (not served, awaiting approval, starting, ready, failed, stopped), its requests and its last session's line; **Serve** (`serve_start`) for a built model not served, **Stop** (two presses) for one starting or ready, **Approve** and **Decline** for one awaiting approval. A row opens the model's serving drawer (`serve:<recipe>`).
- **The serving drawer, and a Serving block in a model's drawer** (Map) for a model that declares `serve`: the state with its reason, the address of the endpoint (`POST /api/serve/<name>/predict`), the controls, the failure's output tail, the timing summary of the session, and **Try it**: a text field holding the inputs as JSON (the declaration's `example`, else `{}`), **Send**, and the answer (outputs, the three times) or the refusal in the server's words.
- **In place.** While a session shown is starting (or awaiting approval), the page asks `served` every second and sets the state mark, the line and the controls of that block in place; when it is ready the controls change from Stop-only to Stop and Try it. Nothing else is read again. Try it does not read the project again.

## 8. Slices

| | Slice | Files |
| --- | --- | --- |
| T6a | The declaration, the protocol, the adapter, the supervisor, the operations, the endpoint | `tuldok_project/serving.py`, `serve_protocol.py`, `serve_adapter.py` (new), `schemas/recipe.schema.json`, `check.py`, `local.py`, `operations.py`, `service.py`, `host.py`, `app.py`, `docs/contracts/project-folder.md`; tests `tests/test_tuldok_project_serving.py` (new), the service test's count |
| T6b | The page | `static/project-workspace/serving.js` (new), `tabs.js` (the section and drawer hooks), `screens.js` (the block in a model's drawer), `base.css` or a new `serving.css`, `project-workspace.html`, `app.py` (assets); `tests/browser_project_workspace_serving.cjs` and its fixture (new) |

## 9. Tests

**Unit:** the declaration (valid, missing environment, a bad name, a missing module file, not `.py`); the protocol's checks (a request of only `inputs`, a valid and a malformed array, its length against its shape, too deep, too large) and the adapter's own encoding and decoding with and without NumPy, run in a child process; the supervisor with a stand-in module: start to ready, a `load` that raises (failed, with its output's tail), a `load` that hangs (failed after `start_seconds`), a request that raises (422, still ready), a request that hangs (504, failed), idle stop, the limit, stop, and no process left after each test; approval (an agent's start awaits the owner; approve; stop declines); the credential checks through HTTP (none: 401; inspect only: predict yes, start no; owner: start and stop).

**End to end:** the buildable fixture with `serve.py` and a `serve` block on `fit-a`, built, served through the owner's start, called through `POST /api/serve/fit-a/predict` with a reader credential (nested lists and a base64 array), refused without one; timings in `serve_session`; `serve_values` into a benchmark of served latency, whose summary rows the test checks against its own arithmetic.

**Browser,** `tests/browser_project_workspace_serving.cjs`: start a served model from its drawer, its state goes to ready in place (the same elements), Try it returns a result, stop it; the Train tab's section; light and dark, 1440 and 390 wide, no sideways overflow, no script error.

## 10. Out of scope

A remote address (decision 4); more than one process per model, batching, streaming answers, GPU scheduling between serving and builds (a served model with `gpu` does not take the GPU lock: doubt); authentication other than Tuldok's credentials; serving a dataset or a benchmark; restarting a failed model on its own.
