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
