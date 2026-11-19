# Implementation spec: the client for the Pumas 0.8.0 endpoint

This is phase 3 of [the data tools plan](data-tools-plan.md). It is built beside phase 1, on the branch `chore/pumas-080-client` in a working tree of its own, because it touches none of phase 1's files. Section 1 of [spec-m1-m2.md](spec-m1-m2.md) applies where it speaks of dependencies, tests, Git and the report; the code here is catalog mode's shared client modules, not `tuldok_project/`.

**Owner, 2026-11-13:** "we will use the pumas endpoint. We wont be embedding pumas."

**After this phase** Tuldok's client speaks the contract Pumas Library 0.8.0 released, and can ask an endpoint what it serves. Nothing new uses it yet: generation and suggestions in a project folder are phase 5. Catalog mode behaves as before.

## 1. Rules

- **An endpoint, never embedded.** Tuldok reaches Pumas by HTTP at an address, and only so. No Pumas code is imported, vendored, started or built by Tuldok. Contract files copied into `tests/fixtures/` as test data are not code and stay.
- **The released contract is the reference.** It is read, read only, from the Pumas Library repository at the tag `v0.8.0`:
  `git -C "/media/jeremy/OrangeCream/Linux Software/repos/owned/ai-systems/Pumas-Library" show v0.8.0:<path>`, for
  `docs/contracts/model-operations-v1.md`, `docs/contracts/image-generation.md`, `docs/contracts/image-to-text-v0.8.md`, `docs/contracts/local-discovery-bootstrap.md`, `docs/adr/0005-modality-primitives.md`, `scripts/consumers/contracts/capability-descriptor.schema.json`, `docs/release-notes-0.8.0.md` and the 0.8.0 section of `CHANGELOG.md`. Nothing in that repository is changed, checked out or built. Its working tree is behind the tag; only `git show` and `git grep` at the tag are used.
- **No running Pumas is contacted.** Everything is checked against fakes made from the released contract. A real endpoint is tried only on the owner's word, in phase 5.
- **Additive tolerance, as the contract asks.** A response field, capability, format, option name, availability reason or modality the client does not know is ignored, not an error. A request never sends what the endpoint did not declare.

## 2. Work

1. **Bring in the earlier work.** Merge `feat/pumas-v080-api` (written on 2 November against the contract as it then stood) into this branch with a merge commit left uncommitted for review, or as plain working-tree changes if a merge cannot be left open; say which. A trial merge had no conflicts.
2. **Compare with the release** and write the differences down, in a table under "As built" at the end of this file: endpoints, request `input` kinds and `output` values, capability names, descriptor fields, error codes and HTTP statuses, byte bounds, the discovery advertisement at `/.well-known/pumas`. For each difference: what Tuldok does today and what was changed.
3. **Close the differences** in `pumas_operations.py`, `pumas_gateway_descriptor.py`, `gateway_discovery.py`, `pumas_vision.py` and `image_generation.py`, and in the fixtures and fakes under `tests/` that stand for the endpoint. The pinned identifiers in those modules (they name pull requests of the pre-release) say which contract they follow; they are updated to say 0.8.0 where the code now follows the release.
4. **What an endpoint serves.** A function in `pumas_operations.py`, with no dependence on the catalog, that reads `GET /v1/served-models` from an address and returns, bounded and validated, each served (model, profile) with its alias, profile, whether the profile must be named, provider, load state, context size, its `modalities` (input and output) and its capability descriptors with availability. Beside it, one that answers for a served model which capabilities are available to make a given output (`text`, `png_base64`, and whatever else is declared) from a given input kind. Both are pure functions over the HTTP transport already used (`ai_http`), tested against a fake.
5. **Catalog mode is unchanged in behaviour:** its pages and operations do what they did; their tests pass.

## 3. Tests

A disposable PostgreSQL, as the rules say (`/tmp/claude-1000/d3/pg`), with `TULDOK_PROJECT_HOME` and `TULDOK_SETTINGS` under `/tmp/claude-1000/d3/`.

- `tests/test_pumas_typed.py`, `test_pumas_vision.py`, `test_pumas_gateways.py`, `test_gateway_discovery.py`, `test_image_generation.py`, `test_ai.py`, and the tests of the modules that call them (`test_synthetic*.py`, `test_caption_proposals*.py`, `test_text_classification_proposals*.py`, `test_grounded*.py`, whichever exist): all pass.
- New tests for section 2.4: a fake `/v1/served-models` with two models (one served by two profiles), an unknown capability and an unknown modality among known ones, an unavailable capability with a reason, a response over the bound, a malformed entry.
- `node tests/test_pumas_gateways_controller.cjs`, `node tests/test_pumas_typed_controller.cjs`; `node tests/browser_pumas_typed.cjs` and `node tests/browser_pumas_gateways.cjs` with Playwright's headless shell if it is found on this machine (say if not run).
- `PYTHONPATH=tests .venv/bin/python -m unittest test_agent_api test_agent_negotiation test_agent_http` from the repository root: the catalog manifest's digest is unchanged.

## 4. Out of scope

Any use of the endpoint from a project folder; where a project keeps the endpoint's address; audio and 3D output (the release reserves audio output and has none for 3D); decisions, rerank, embeddings and transcription as Tuldok features (the served-models answer lists them; nothing calls them yet).

## As built

The earlier work (`feat/pumas-v080-api`, written against the pre-release `4c79cd8e`) was merged with `git merge --no-commit --no-ff` and left open. It was then compared with Pumas Library `v0.8.0` (commit `69e32a2208c5c2d840f4adafec03350669fcb5bc`), read with `git show` only. "Earlier client" below means the merged state before this phase's changes.

| Area | Released contract (0.8.0) | Earlier client | Done |
| --- | --- | --- | --- |
| Endpoints | `GET /v1/served-models`, `GET /v1/capabilities`, `POST /v1/model-operations`; `/v1/models` lists each ID once with `profiles`; `POST /v1/images/generations`; `GET /.well-known/pumas` | All used. `/v1/served-models` was read only for (model, profile) pairs to fill a model list | New `served_models()` and `available_capabilities()` (2.4). The listing for catalog forms is unchanged |
| Request `input` kinds and `output` | Kinds `text`, `text_batch`, `messages`, `image_messages`, `image`, `content_batch`, `decision`, `rerank`, reserved `audio`; outputs `text`, `embeddings_float32`, `png_base64`, `decisions`, `relevance_scores`, reserved `labels`, `pcm_*`. Message content is a string or parts; parts gain `audio` | Sends `messages` (string content), `image`, `messages`/`image_messages` with text and image parts; outputs `text`, `png_base64`. All still valid | No change to requests. `INPUT_KINDS` maps each kind to the descriptor formats the release's resolver matches, for `available_capabilities()` |
| Results | `text` (finish `stop`/`length`/`content_filter`), `embeddings`, `image`, `decisions`, `relevance_scores` | Decodes `text` and `image`; refuses a finish other than `stop` as incomplete (outcome `unknown`) | No change: Tuldok applies only complete text and requests no other result kind |
| Capability names | Ten, adding `rerank` (and `audio_transcription`, `audio_classification`) | Selects `chat_generation`, `image_generation`, `image_to_text` by name; ignores others | No change to selection. Release vocabulary recorded in `CAPABILITIES`; fixtures gain `rerank` |
| Descriptor fields | Required `input_modalities`, `output_modalities` per descriptor; `modalities {input, output}` per serving | Not read (tolerated) | Read and validated by `served_models()`; fixtures carry them. `/v1/capabilities` decoding still does not require them |
| Option names | Adds `total_image_bytes`, `message_count`, `content_parts`, `input_tokens`, `top_n`, audio bounds | Compared `max_tokens`, `temperature`, `top_p`, `width`, `height`, `seed`, `image_bytes`, `image_pixels`, `image_count` | Image→Text also checks `total_image_bytes`, `message_count`, `content_parts`; typed image generation checks `input_characters` against the prompt. Both only when advertised |
| Availability reasons | Closed set `unsupported_adapter`, `unknown_model_task`, `model_task_mismatch`, `runtime_unavailable` | Any string shown; fixtures used the pre-release `unqualified_audio_runtime` | Fixtures use release reasons. Unknown reasons still shown as text, never interpreted |
| Error shape | `{contract_version, request_id, error:{code, outcome, message}}`; pre-handler refusals are `{"error":{"code","message"}}` | Pre-handler body on `/v1/model-operations` was read as malformed (outcome `unknown`, code lost) | Decoded as a typed refusal, `not_admitted`, code kept. `ai_http` also shows the `message` of a typed error (e.g. from `/v1/served-models`) |
| Error codes and statuses | Twelve codes, status per code (400/404/409/413/422/503/502) | Codes kept verbatim; `outcome` authoritative, status recorded as evidence | No change |
| Byte bounds | Request/response 32 MiB, stream event 256 KiB; images 8 MiB each, 16 MiB total, 4 images, 4096 px, 4 Mpx; 128 messages/parts; message ≤ 1024 bytes | Same bounds locally; responses read under the lesser of Tuldok's and the advertised bound | No change. `served_models()` reads at most 8 MiB and 4096 entries |
| Image generation | Width/height bound 1–2³²−1 (no allowlist); `memory_policy` gains `scaled_fp8_to_bf16_sequential_cpu_offload`; errors `{"error":{"type":"pumas_error",code,message}}` with 400/409/499/502/503/507 | Typed path caps at 2048 px/side, 4 Mpx (Tuldok's own limit); legacy path dropped unknown memory policies | Cap kept (Tuldok policy, within the release bound). Any `[a-z0-9_]{1,64}` memory policy is now kept |
| `/.well-known/pumas` | `HttpServiceDescription`, `InstanceDescription`, `PumasBuildInfo` as at the tag | Same fields and types; `service_generation` limited to 128 characters | Limit raised to 256, as the release's reference consumer allows. Fixture unchanged (its shape matches the release) |
| Pins | — | `pumas_operations.SOURCE_COMMIT` = `4c79cd8e…`, `pumas_gateway_descriptor.SOURCE_COMMIT` = `80f06ab1…` (PR51) | Both `69e32a22…` (`v0.8.0`); `pumas_vision` follows `pumas_operations` |
| Fixtures | Only `capability-descriptor.schema.json` is published at the tag | Six schemas exported at `4c79cd8e` | Descriptor schema replaced by the release copy (its digest equals the one the release's consumer reference pins); `capabilities-response` and a new `served-models-response` derived from it and `types.rs`; the other four kept, marked in `source.json` |

Notes on the spec:

- 2.4 says the functions run "over the HTTP transport already used (`ai_http`)". The typed module's other GETs use `gateway_discovery.get_json`; `served_models()` uses `ai_http.request` as written, so it takes any HTTP(S) address (a trailing `/v1` is accepted), not only numeric loopback. `available_capabilities()` makes no request.
- "Whatever else is declared" is read as the release's output formats. An output or input kind outside them raises `ValueError`, since unknown values are dropped from descriptors.
- A malformed entry refuses the whole listing, naming the entry, as the other decoders in these modules do; unknown values within an entry are dropped.
