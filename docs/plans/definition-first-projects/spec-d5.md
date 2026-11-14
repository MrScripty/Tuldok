# Implementation spec: generating datasets and suggesting annotations through the Pumas endpoint

This is phase 5 of [the data tools plan](data-tools-plan.md). It builds on [spec-d3.md](spec-d3.md) (the client for the Pumas 0.8.0 endpoint) and [spec-d4.md](spec-d4.md) (annotation, and the steps Tuldok provides). Section 1 of [spec-m1-m2.md](spec-m1-m2.md) applies; the page follows [spec-w4.md](spec-w4.md).

**Owner, 2026-11-13:** "we will use the pumas endpoint. We wont be embedding pumas." And: "Right now we just need the basic modality support for data generation and annotation. text, image, audio, 3D (point clouds, mesh). ... This is more a setup so other projects can setup what they need to generate."

**After this phase** a project can make a dataset by asking a model that a Pumas endpoint serves, as an ordinary build, and a person annotating can ask such a model for a suggestion and accept or change it. Tuldok offers what the endpoint says it serves and nothing else.

## 1. What an endpoint can do, and what Tuldok offers

Pumas Library 0.8.0 produces **text** (`chat_generation`, `text_generation`) and **PNG images** (`image_generation`); it reads images (`image_to_text`), decides between choices on text, images and audio (`decision`), and transcribes speech (`audio_transcription`). Its contract reserves audio output and has nothing for 3D.

Tuldok hard-codes none of that. Every offer on the page and every check before a call comes from `GET /v1/served-models` at that moment: a model is offered for a use when one of its capabilities is available and takes the input and makes the output the use needs. So:

| Wanted | Through the endpoint today | Otherwise |
| --- | --- | --- |
| A text dataset | yes | a project's own command, or `import` |
| An image dataset | yes | the same |
| An audio dataset | no: no served model declares audio output | a project's own generator command, as an ordinary build writing `records.jsonl`; or `import` |
| A point cloud or mesh dataset | no: the contract has no such output | the same |
| A suggestion for a text, an image, a sound | where a served model's capability fits (section 4) | none |
| A suggestion for a point cloud or a mesh | no: no model takes them | none |

When Pumas gains an output, the generation form and the step need only know how to store it as a record; the offer appears by itself. This phase stores `text` and `png_base64`.

## 2. The endpoint is a setting of the machine

- The address is in Tuldok's settings file beside the project directory: `pumas_endpoint`, an `http` or `https` address, or absent. It is never in the Git folder and never in a definition.
- **Operations:** `endpoint` (inspect): the address, whether it answered, and what it serves (each model and profile with its modalities and the capabilities available), or the reason it did not answer. `set_endpoint` (owner, changes): sets or clears the address; it is checked by asking it once. `find_endpoints` (owner): the Pumas endpoints advertising themselves on this machine, found as catalog mode finds them, for the owner to pick from.
- A call to the endpoint is bounded in time and bytes as the client already bounds it, and is made outside the service's lock.
- **One module of `tuldok_project/` imports the client** (`pumas_operations`, `image_generation`, `gateway_discovery`, `ai_http`): a new `tuldok_project/pumas.py`, as `host.py` is the one that imports the app's access layer. Nothing of Pumas is imported, bundled or started.

## 3. The step `generate`

A dataset whose `run` has `step: "generate"`, like `import` and `freeze` (spec-d4 section 6), with settings:

| | |
| --- | --- |
| `make` | `text` or `image` |
| `model`, `profile` | the served model's alias, and its profile when the endpoint requires one |
| `prompt` | the request, with `{n}` (the item's number from 1) and, with an input, `{text}` |
| `count` | how many to make, 1 to 100,000; not with an input |
| `per` | with an input: how many for each of its records, default 1 |
| `seed` | an integer; item `n` is asked with `seed + n - 1` where the capability takes a seed |
| `options` | the capability's own options (`max_tokens`, `temperature`, `top_p`, `width`, `height` and what else it declares), checked against the bounds the endpoint advertises |
| `rights` | required: a sentence on what may be done with the output |

- **An input.** `inputs: {"prompts": <a dataset>}` makes one request for each text record of that dataset's product (times `per`), in the product's order: a dataset of prompts written by hand, imported, or itself generated can drive a dataset of images.
- **Output:** `records.jsonl` and, for images, the files under `files/`. Each record has its `id` (`g000001` and on), `kind`, `text` or `path`, `sha256`, `bytes`, `rights` and `origin`: `{"generated": {"model", "profile", "capability", "prompt", "seed", "options", "input"}}`, where `seed` is null when the capability took none and `input` is the prompting record's id.
- **Before anything is asked,** the step reads what the endpoint serves and fails, saying why, when the model is not served, the capability is not available, or an option is outside its bounds.
- **A request that fails.** One refused before the provider took it (`not_admitted`) is asked again, twice at most, after a pause. Anything else, or a third refusal, fails the step with the item's number and the endpoint's reason; what was made stays in the failed run's directory and is no product.
- **Where the endpoint comes from.** The build passes the machine's `pumas_endpoint` to the step. With none set, a plan marks the step as not buildable and says so, as it does for an environment that is not ready. The run's record keeps the address and the endpoint's reported version; neither goes to Git.
- **Progress** is the count made; a cancel stops the step between or during a request, as any run.
- **Who may start it** is who may start any build: an agent's request waits for the owner. Generation works the machine that runs Pumas; the approval is the owner's say over that.
- A generated dataset is **rebuilt** only when its definition or its input changes. Building it again may not give the same content (a model need not be deterministic); annotations are tied to content, so those that no longer fit are marked stale (spec-d4 section 3).

## 4. Suggestions

`suggest_annotation` (who: edit; it changes nothing): `task`, `record`, `model`, `profile`, and an optional `instruction`. It answers `suggestion`: a `value` in the task's form and `from`: `{"model", "profile", "capability"}`. Nothing is stored. The page puts the value in the form; when the person keeps it, `set_annotation` carries `from`, and the line in Git names the model.

| Task | Record | Asked as |
| --- | --- | --- |
| `text` (a caption) | image | `image_to_text` |
| `text` (a transcript) | audio | `audio_transcription`, where the released contract gives a request for it; else none |
| `text` (a summary) | text | chat |
| `class`, `tags` | text, image, audio | `decision` over the vocabulary, where a served model offers it for that input; else, for text and images, chat or `image_to_text` asked to answer with terms only, and the answer kept only when it is made of terms |
| `review`, `boxes`, `spans`, `segments` | any | none in this phase |

`suggestion_models` (inspect): for a task, the served models that can suggest for each kind of record it has, so the page offers only those. A suggestion that is not a valid value of the task is answered as a refusal with the model's words, never as a value.

## 5. The page

- **Train tab, beside the environments:** the endpoint. Its address, whether it answers, the models it serves with what each takes and makes. The owner sets, clears or finds it.
- **Data tab, a form "Generate":** name, what to make, the model (those that can make it), the prompt, a count or a dataset of prompts, seed, the options the chosen capability declares with their bounds, rights. It keeps a dataset definition as an unsaved edit; building it is the existing plan and request. With no endpoint, or none that can make anything, the form says so.
- **Annotate tab:** "Suggest" beside the form when a served model fits the task and the record, with the model as a select. While the model answers the button says so and can be cancelled; the suggestion fills the form marked as a suggestion until the person changes or keeps it. "Suggest for this page" asks for the records on screen that have no annotation, one after another, as drafts.

## 6. Slices

| | Slice | Mainly |
| --- | --- | --- |
| D5a | The setting, `pumas.py`, the three endpoint operations, the step `generate` | `tuldok_project/local.py`, `pumas.py`, `steps.py`, `builds.py`, `plan.py`, `check.py`, `schemas/`, `operations.py`, `service.py` |
| D5b | `suggest_annotation`, `suggestion_models` | `tuldok_project/pumas.py`, `annotation_records.py`, `operations.py`, `service.py` |
| D5c | The endpoint on the Train tab, the Generate form, Suggest in Annotate | `static/project-workspace/` |

## 7. Tests

Everything is checked against a fake endpoint built from the released contract (`tests/fake_pumas_typed.py` and what spec-d3 added). No running Pumas is contacted.

- **D5a:** the setting set, cleared and refused when it does not answer; `endpoint` with two models and an unavailable capability; a text dataset and an image dataset generated for real through the build machinery against the fake, with their records, hashes and `origin`; from a dataset of prompts, with `per`; seeds passed and recorded, and null where none is taken; an option out of bounds, a model not served and a capability unavailable each fail before any request; a `not_admitted` refusal retried and then failed; another failure failing at once with the item's number; no endpoint set: the plan says so; nothing of the address in the Git folder.
- **D5b:** each row of section 4's table against the fake; an answer that is not made of terms refused; no model fitting: none offered.
- **D5c,** a browser check with the fake: the endpoint set from the page and its models listed; the Generate form writing a definition that checks; a suggestion asked, shown, changed and kept, and the saved line naming the model.

**A real endpoint** is tried once, on the owner's word: one small text dataset and one small image dataset through the Pumas the owner runs, and one suggestion. It uses that machine's GPU for a moment.

## 8. Out of scope

Audio and 3D output (nothing serves them); video; embeddings, rerank and similarity search over a dataset; continuing a generation that failed part way; a queue of suggestions that outlives the page; choosing among several endpoints.

## As built

### D5a and D5b

What differs from the text above, and what was chosen where it was silent.

- **The address is a numeric-loopback HTTP address.** Section 2 says "an `http` or `https` address". The settings file accepts that (`local.endpoint_problem`), but `set_endpoint` keeps only what the client can send a model operation to: `pumas_operations.exchange` takes a credential-free numeric-loopback `http` base (`pumas_gateway_descriptor.endpoint`), which is also what Pumas 0.8.0 binds (`local-discovery-bootstrap.md`). Anything else is refused `invalid` before any request. Supporting `https` or a host name needs a change to the client's exchange, not to `pumas.py`.
- **`pumas.py` imports `pumas_operations`, `image_generation`, `pumas_vision` and `gateway_discovery`**; `ai_http` is reached through `served_models`. No other module of `tuldok_project/` imports any of them; `steps.py` imports `pumas.py` inside `generate_records` only.
- **One additive change to the client:** `pumas_operations.result` decodes a `decisions` result (`{kind, answers}`, answers read by the caller) and `exchange` checks the result kind through `RESULT_KINDS`, which adds `decisions`. Catalog mode never asks for that output; its tests pass unchanged.
- **The fake** (`tests/fake_pumas_typed.py`) gained three optional state keys: `modes` (one mode per POST, before `mode`), `respond(body)` (the `result` of a successful POST) and `advertise` (a version for which `/.well-known/pumas` answers with the advertisement fixture at the fake's own address). Without them it answers as before.
- **The endpoint's version** is `build_info.package_version` of its `/.well-known/pumas`, or null when it has none. The step writes `{address, version}` to `<run>/endpoint.json` (beside `output/`, not in the product) and the build keeps it in a new column `runs.endpoint`, set to `{address, version: null}` when the run is recorded and completed from the file when it ends. The address also appears in the run's `argv`. Neither is in the folder; a test scans the folder and `git log -p` for it.
- **No endpoint set.** A plan marks a `generate` that would be built `blocked`, with one cause, itself, `rebuild: "endpoint"` and the reason, and a note; it is added to `blocked_targets` even when it is not a target (so `execute` refuses the plan before anything runs) and `buildable` is false. The settings file is read for this only when such a step is in the plan, through a function `make_plan` takes as `endpoint`: spec-m4's rule that making a plan opens no file (a test of it) still holds for every plan without a generate. A setting cleared after the plan was made fails the step before it starts (`StepProblem`).
- **The capability** is the first of the served model's available capabilities, in the endpoint's order, that makes the output from `text` (`available_capabilities(entry, 'text', output)`); the request's input is always `{"kind": "text"}` with `capability` named. With the vision fixture's models that is `chat_generation` before `text_generation`.
- **Options.** Only the names of the capability's options kind in the released grammar are sent (`text_generation`: `max_tokens`, `temperature`, `top_p`; `image_generation`: `width`, `height`, and `seed` from the setting). An option must be advertised with a bound and lie within it; `width` and `height` are required for an image, and the client's own cap (2,048 px a side, 4 Mpx) applies. A capability whose options kind Tuldok does not know is offered and asked with no options.
- **The seed** is sent only when the capability's options kind has one and the endpoint advertises a `seed` bound; `seed + count − 1` is checked against it before anything is asked. For an image `origin.seed` is the seed the endpoint reports it used (also when the setting has none); for text it is null.
- **Bounds not in the text:** at most 100,000 items in all, also with an input (records × `per`); `per` 1 to 1,000; `prompt` 1 to 16,000 characters, checked against an advertised `input_characters` per item before anything is asked; `seed` 0 to 2³²−1; `options` at most 32 numbers, `seed` not among them.
- **A text too long for one line** of `records.jsonl` (64 KiB) is written as `files/<id>.txt` with `path`; the client reads at most 256 KiB of a text result.
- **The pauses** before asking again an item refused `not_admitted` are 1 s and 2 s. Every `not_admitted` outcome is asked again, as the text says, whatever its code. Each attempt has its own `request_id`.
- **An input of prompts** gives its text records only, inline or a UTF-8 file of at most 64 KiB in the product; others are skipped and counted. An input shown through a `view` is refused, as for `freeze`.
- **`set_endpoint`** writes an activity row (`set` or `cleared`, the address not in it). `find_endpoints` is the owner's and is not a mutation, so it writes none. `suggest_annotation` is `edit` and not a mutation: nothing is stored and no row is written.
- **Suggestions.** No options are sent (the capability's defaults apply). A suggestion is given up after 300 s (`pumas.SUGGEST_SECONDS`) by the client's own cancel. A record is read whole up to 16 MiB; an image must be PNG or JPEG and pass `pumas_vision.image_part`; a sound must be a 16-bit PCM WAVE of one or two channels, 8 to 192 kHz and at most 30 s (sent as `pcm_s16le`), since Pumas parses no container. Advertised image and audio bounds are checked when advertised. A caption's default instruction is "Describe this image in one or two sentences.", a summary's "Summarize this text in a few sentences."
- **Refusals of `suggest_annotation`:** `unavailable` (no endpoint, it did not answer or refused, the model cannot suggest for this record), `not-found` (model or profile not served, record not in the product), `invalid` (a model served with two profiles named without one; content that cannot be sent) and a new code, `unsuitable` (409), for an answer that is not a value of the task, with the model's words quoted (at most 400 characters).
- **Terms only.** `class` keeps the whole answer, trimmed of spaces, quotes and a final full stop, when it is a term exactly. `tags` takes the whole answer as one term when it is one, else splits it on lines and commas (a term holding a comma is then lost), trims list marks, and keeps it only when every piece is a term; the value is in vocabulary order. Case is not folded.
- **Decisions.** `class` asks one `choice` question `class` with the vocabulary as `criteria`; `tags` one `noul` question per term, `t0`, `t1`, …, and keeps the terms above 0.5. `state` is the record's text, or the instruction (default "Decide for the content given.") with `images` or `audio`.
- **`suggestion_models`** answers the kinds the product has that the task annotates (none without a product), each with every served (model, profile) that fits, and `problem` instead of a refusal when there is no endpoint or it does not answer.

Section 4's table, as built:

| Task | Record | Offered | Request |
| --- | --- | --- | --- |
| `text` (caption) | image | yes, where `image_to_text` is available for `messages_image` | `capability: image_to_text`, `input: {"kind": "image_messages", "messages": [{"role": "user", "content": [{"kind": "text", "text": <instruction>}, {"kind": "image", "encoding": "png"\|"jpeg", "data_base64": …}]}]}`, `output: text` |
| `text` (transcript) | audio | yes, where `audio_transcription` is available for `pcm_s16le`/`pcm_f32le` | `capability: audio_transcription`, `input: {"kind": "audio", "encoding": "pcm_s16le", "sample_rate_hz", "channels", "sample_count", "data_base64"}`, `output: text`, no options. The contract's "Audio transcription" section gives this input; its request grammar still calls the `audio` kind reserved, and no options kind is named for it, so none is sent |
| `text` (summary) | text | yes, where `chat_generation` is available for `messages_text` | `capability: chat_generation`, `input: {"kind": "messages", "messages": [{"role": "system", "content": <instruction>}, {"role": "user", "content": <text>}]}`, `output: text` |
| `class`, `tags` | text, image, audio | yes by `decision`, where it is available and its `input_modalities` hold the record's modality | `capability: decision`, `input: {"kind": "decision", "state", "questions", "images": [{"encoding", "data_base64"}] \| "audio": [clip]}`, `output: decisions`. The shape of a decision image is not written out in the contract's text (only that audio clips have no `kind`); it is the released DTO `DecisionImage {encoding, data_base64}` (`types.rs` at `v0.8.0`) |
| `class`, `tags` | text | else by `chat_generation`, terms only | as the summary, the instruction asking for terms of the listed vocabulary |
| `class`, `tags` | image | else by `image_to_text`, terms only | as the caption, likewise |
| `class`, `tags` | audio | only by `decision`; no fallback, as the text says | |
| `review`, `boxes`, `spans`, `segments` | any | no | |
| any | point cloud, mesh, array, file | no | |

- **Tests:** `tests/test_tuldok_project_pumas.py`, 29: the check (4), the settings file (2), the routes and offers from descriptors alone (2), `endpoint`/`find_endpoints` on the fake with the scanner patched (3), and against a database: the setting set, cleared, refused and its activity (3), a text dataset and an image dataset from a dataset of prompts with `per` and seeds generated by `builds.execute`, an option, a model and a capability each failing before any request, `not_admitted` asked again twice then failing, another failure failing at once at item 2 (5), each row of the table, answers not made of terms or not in the vocabulary refused, no model fitting, and a kept suggestion's `from` in the saved line (8), and the step alone (2). `test_tuldok_project_service.py`: 59 operations, `set_endpoint` a mutation, `set_endpoint` and `find_endpoints` the owner's, the new reads in `test_every_read`. The catalog profile's digest is unchanged; the project_folder profile has the five new operations.
- **Not verified:** a real Pumas (the owner's word is needed, section 7); a decision model's, a Torch transcription runtime's and a vision model's real answers (the fake answers what the contract describes); `https` and host-name addresses (refused); cancelling a generate during a request (the launcher's cancel stops the process, as for any run; not tested here); 100,000 items; a JPEG or stereo sound sent for a suggestion; the page (D5c).
