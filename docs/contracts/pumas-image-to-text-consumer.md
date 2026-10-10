# Pumas Image→Text consumer

This opt-in caption path consumes the contract at Pumas Library merged PR68,
source `36c2aab2c885b8416fd4e39cf8c37c510596d6e4`:
[Image→Text contract](https://github.com/MrScripty/Pumas-Library/blob/36c2aab2c885b8416fd4e39cf8c37c510596d6e4/docs/contracts/image-to-text-v0.8.md).
It is based on Tuldok main `d99e23d2b0d2783a7a9863232a7453cd9f2db7aa`.
The legacy compatible caption path and the previous typed text/image operations
remain available. Their existing producer receipt is not silently repinned.

`pumas_operations.validate_manifest` accepts all seven closed capability variants,
the three additional image input formats and image byte/pixel/count option names.
The existing unavailable reasons remain unchanged. Availability is a live
observation, not a model qualification receipt. Audio's existing
`max_output_tokens` descriptor option is accepted as declared in the inspected DTO.

Choose **Pumas typed v1** in the image caption form, select the serving alias and
optional exact profile, and inspect capabilities. On each new attempt, the owner
requires `pumas.model-operations.image-to-text:1` in the gateway build advertisement
and an available Image→Text descriptor for the exact resolved model/profile.
The request uses the facade's `messages`, `semantic_task:"image_to_text"`,
text-generation options and `stream:false`. The seed is omitted. Named image and
`image_messages` inputs are also supported by the bounded consumer request builder.
Ordered roles/parts and original compressed bytes are preserved. Only user
messages can contain images; audio, URLs, paths and data-URL envelopes are refused.

The consumer applies the producer's 32 MiB whole-request, 8 MiB per-image, 16 MiB
aggregate, four-image, 4096-axis, 4,194,304-pixel, 128-message and 128-total-part
bounds. Tokens default to 512 and permit 1–2048; temperature/top-p must be finite
and within 0–2/0–1. The caption application's existing preparation is smaller:
one RGB JPEG, at most 2 MiB and 1600 pixels on its longest side. It decodes the
captured, hash-verified canonical image and retains both canonical-source and
prepared-input hashes. Preparation is explicit in request history.

Local preflight checks canonical standard base64, complete still containers,
PNG CRCs, declared encoding, dimensions and Pillow raster decoding. It does not
replace Pumas's production PNG/turbojpeg validation, allocation controls or
admission authority, and does not claim equivalent JPEG warning detection.
No local validation result is used as permission to bypass provider refusals.

The response is the closed `{contract_version, request_id, result}` envelope.
The request ID must match; `result.kind` must be text. There is no response-model
requirement and no private provider envelope projection. This application requires
a complete `stop` finish reason and valid caption JSON within a 256 KiB response
bound; partial or filtered output is not applied. Capability/build observations,
contract source, canonical request/hash and raw response/hash remain inspectable
on the exact job. List responses omit image-bearing canonical requests and raw
bytes. Explicit application creates a draft target and records its evidence in
revision history; human review remains separate.

HTTP 400/413/422/503 pre-admission refusals and 502 failures retain their typed
code, HTTP status and `outcome` in the asynchronous job. A disconnect, uncertain
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
a captured native DTO schema export or an actual model reply. The tests exercise
seven-capability parsing, named/facade PNG/JPEG inputs (including progressive
JPEG), order, closed shapes, finite/resource bounds, typed application captions,
draft/history, live selection refusal, cancellation/borrowed-owner survival,
HTTP outcomes, restart and no replay. The existing typed browser suite additionally
checks the actual caption form, capability inspection, application and disconnect.

The six actual production DTO schemas regenerated from the combined source
are retained in `tests/fixtures/pumas-image-to-text-v1/schemas/`, with SHA-256
identities in `source.json`. The source-derived capability fixture and authored
named/facade image requests and typed responses validate against these exports.
The schemas describe wire shape; finite bounds and live readiness remain runtime
checks. Neither fixture output nor schema validity proves native inference.

The reviewed producer retains identical DTO definitions and schema dependencies;
all six exported schema SHA-256 identities are unchanged. `source.json` records
the export commit and refreshed handler/controlled-test source hashes. The fixture
gateway advertisement reads the same versioned source pin as its consumer
acceptance evidence.
This pin is the immutable merged Pumas main commit. Its source tree is identical
to the reviewed producer that passed CI before the coordinated merge.
The combined desktop contract and packaged application are provider integration
gates. Real model/projector inference, semantic quality, managed native teardown
and production audio qualification remain unclaimed. No models or runtimes are
acquired by this consumer. Existing historical text/image fixture receipts retain
their original source identities.
