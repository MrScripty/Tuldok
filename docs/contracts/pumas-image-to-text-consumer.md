# Pumas Image→Text consumer

This opt-in caption path, and the typed text and image operations that share
`pumas_operations`, consume the Pumas Library v0.8 typed HTTP contract on branch
`feat/v080-consumer-api`, source `4c79cd8e35db566b70caaa13d8d8f92265f5976e`:
[model operations, contract version 1](https://github.com/MrScripty/Pumas-Library/blob/4c79cd8e35db566b70caaa13d8d8f92265f5976e/docs/contracts/model-operations-v1.md).
It supersedes the merged PR68 pin `36c2aab2c885b8416fd4e39cf8c37c510596d6e4`,
which `source.json` keeps as `previous_producer`. The legacy compatible caption
path remains available. The PR54 typed text/image capture receipt in
`tests/fixtures/pumas-typed-v1` is historical and is not repinned.

### Additive compatibility

Pumas responses grow additively within contract version 1. Tuldok validates
only what it uses and selects capabilities and option bounds by name, never by
position or count:

- `GET /v1/capabilities` requires `supported_contract_versions` containing 1,
  `model`, an exact `profile`, positive `max_request_bytes`/`max_response_bytes`
  and a `capabilities` list. Other fields (`context_tokens`,
  `max_stream_event_bytes`, future fields) are retained but not required.
- Only `chat_generation`, `image_generation` and `image_to_text` descriptors are
  validated: fixed semantic task, string format lists, an availability `state`
  with an optional string reason, and finite, ordered bounds for the options
  Tuldok compares (`max_tokens`, `temperature`, `top_p`, `width`, `height`,
  `seed`, `image_bytes`, `image_pixels`, `image_count`). A used capability or
  option advertised twice is refused as ambiguous.
- Other capabilities (`multimodal_embedding`, `decision`, audio, future values),
  formats (`content_batch`, `decision`, `decisions`, future values), option names,
  availability states and reasons, and response or result fields are ignored.
  Any availability other than `available` means unavailable, and its reason is
  shown.
- The capability observation is bounded at 1 MiB. `GET /v1/served-models` is
  preferred for listing serving aliases with their profiles; gateways without it
  (HTTP 404) fall back to `/v1/models`, which lists each ID once with `profiles`.

Availability is a live observation, not a model qualification receipt.

Choose **Pumas typed v1** in the image caption form, select the serving alias and
optional exact profile, and inspect capabilities. On each new attempt, the owner
requires `pumas.model-operations.image-to-text:1` in the gateway build advertisement
and an available Image→Text descriptor for the exact resolved model/profile. The
gateway advertisement keeps its own closed, versioned decoder: it is retained as
evidence, so unknown advertisement fields are refused rather than stored.
The request uses the facade's `messages`, `semantic_task:"image_to_text"`,
text-generation options and `stream:false`. The seed is omitted. Named image and
`image_messages` inputs are also supported by the bounded consumer request builder.
Ordered roles/parts and original compressed bytes are preserved. Only user
messages can contain images; audio, URLs, paths and data-URL envelopes are refused.

The consumer applies the producer's 32 MiB whole-request, 8 MiB per-image, 16 MiB
aggregate, four-image, 4096-axis, 4,194,304-pixel, 128-message and 128-total-part
bounds. Tokens default to 512. Pumas no longer caps Image→Text `max_tokens` at
2048; the live `max_tokens` bound follows the served context window and is
checked before admission. Temperature/top-p must be finite and within 0–2/0–1.
Advertised image byte, pixel, count and dimension bounds are checked when present. The caption application's existing preparation is smaller:
one RGB JPEG, at most 2 MiB and 1600 pixels on its longest side. It decodes the
captured, hash-verified canonical image and retains both canonical-source and
prepared-input hashes. Preparation is explicit in request history.

Local preflight checks canonical standard base64, complete still containers,
PNG CRCs, declared encoding, dimensions and Pillow raster decoding. It does not
replace Pumas's production PNG/turbojpeg validation, allocation controls or
admission authority, and does not claim equivalent JPEG warning detection.
No local validation result is used as permission to bypass provider refusals.

The response is the `{contract_version, request_id, result}` envelope; added
fields are ignored. The request ID must match; `result.kind` must be text. There is no response-model
requirement and no private provider envelope projection. This application requires
a complete `stop` finish reason and valid caption JSON within a 256 KiB response
bound; partial or filtered output is not applied. Capability/build observations,
contract source, canonical request/hash and raw response/hash remain inspectable
on the exact job. List responses omit image-bearing canonical requests and raw
bytes. Explicit application creates a draft target and records its evidence in
revision history; human review remains separate.

Every typed error is `{contract_version, request_id, error:{code, outcome, message}}`.
`error.outcome` is authoritative: `not_admitted` records no provider effect and
anything else is `unknown`, whatever the HTTP status. 404 `model_not_found` and
409 `ambiguous_model`/`ambiguous_operation` are ordinary refusals. An error whose
`request_id` is `null` (Pumas could not read the body) is still a typed refusal.
Unknown error codes are kept verbatim. The job retains the code, HTTP status and
outcome, and its error text includes Pumas' `error.message`, bounded and on one
line. Capability refusals show the same message. On the OpenAI-compatible routes,
a `pumas_error` body's `error.message` is shown after the existing redaction. A disconnect, uncertain
response or possibly dispatched interrupted attempt remains `unknown`. Repeating
an existing exact application request ID returns the retained attempt; it never
replays inference. A new attempt requires a new explicit request. Browser recovery
retains the exact protocol/profile/seed-null intent alongside existing revisions;
changing its intent cannot turn an uncertain acknowledgement into a retry.

Cancellation disposes the owned HTTP socket, retires its cancellation actor and
joins the caption worker before owner cleanup returns. The borrowed gateway is
kept alive. External HTTP cancellation does not attest native computation stopped.
This consumer launches no Pumas child/session; managed process/projector drainage
and packaged application acceptance remain integration-lead/provider-owner gates.

## Evidence and coordinated review

`tests/fixtures/pumas-image-to-text-v1/source.json` labels the capability/wire
fixture as **source-derived**, with inspected production-source hashes. It is not
a captured native DTO schema export or an actual model reply. The fixture follows
the pinned descriptor construction for a llama.cpp vision serving with an
8192-token context, including the `multimodal_embedding` and `decision`
descriptors. The tests exercise additive capability parsing, named/facade PNG/JPEG inputs (including progressive
JPEG), order, closed shapes, finite/resource bounds, typed application captions,
draft/history, live selection refusal, cancellation/borrowed-owner survival,
HTTP outcomes, restart and no replay. The existing typed browser suite additionally
checks the actual caption form, capability inspection, application and disconnect.

The six actual production DTO schemas regenerated at the pinned source with the
`export-contract` feature are retained in
`tests/fixtures/pumas-image-to-text-v1/schemas/`, with SHA-256 identities in
`source.json`. All six changed from the PR68 export (new capabilities, formats,
`context_tokens`, decision and content-batch DTOs and the required error
`message`). The
source-derived capability fixture and authored named/facade image requests and
typed responses validate against these exports in the vision tests. The schemas
describe wire shape; finite bounds and live readiness remain runtime checks.
Neither fixture output nor schema validity proves native inference.

`source.json` records the branch, commit, tree, contract document hash and
handler/controlled-test source hashes. The pin is a branch commit, not a merged
Pumas main commit; repin when it merges. The fixture gateway advertisement reads
the same versioned source pin as its consumer acceptance evidence.
The combined desktop contract and packaged application are provider integration
gates. Real model/projector inference, semantic quality, managed native teardown
and production audio qualification remain unclaimed. No models or runtimes are
acquired by this consumer. Existing historical text/image fixture receipts retain
their original source identities.
