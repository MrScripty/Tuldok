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
