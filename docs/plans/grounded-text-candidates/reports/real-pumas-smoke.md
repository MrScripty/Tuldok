# Real Pumas integration smoke — 2026-10-02

Bounded real-runtime exercise of the accepted transport repair (`ec24fa84b3f32872cedec94fa990c2c10187a171`). This is integration evidence, not model-quality acceptance. Only fictional text was sent to an already-installed local model. No downloads, paid providers or user assets were used.

## Runtime and reproduction

The released Lanternwake qualification runtime was reused with its existing local registry: official Pumas RPC sidecar, installed llama.cpp `b11352+cpu`, Qwen2.5-0.5B-Instruct Q4_K_M GGUF, two CPU cores, 4096 context, zero GPU layers. Pumas was bound to `127.0.0.1:8765`; its existing managed backend was on `127.0.0.1:8766`. Fresh `get_installed_versions`, `validate_model_serving_config`, `serve_model` and `get_serving_status` responses confirmed the pinned installation and loaded model. No installation fallback ran.

Artifact SHA-256:

- Pumas sidecar: `faaf57ad46101fa479506f78781b17e467cf0365b6632966546fd0cef1693130`
- GGUF: `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`

With the already-configured gateway running, invoke:

```sh
python3 scripts/qualify_grounded_local.py --url http://127.0.0.1:8765 --model lanternwake-dialogue
```

The script accepts a credential-free loopback gateway, creates a temporary fictional dataset, uses production discovery/proposal/review code, reports outcomes, and removes its temporary dataset. It neither launches a runtime nor installs a model. Runtime startup and shutdown remain the caller's responsibility. The script does not assert that every model produces a valid candidate; inspect its reported statuses.

## Observed results

- Real `/v1/models` discovery returned `lanternwake-dialogue`.
- Production request used seed 42 and requested one rewrite of “Please cancel my meeting.” with reviewed class `cancel`.
- The model completed HTTP/chat output with `finish_reason: stop`, but copied placeholder-like schema content: text `...`, label `the supplied source class`, and quote `cancel source text` at offsets 0–5. Production validation correctly rejected the changed class. No candidate or draft was admitted. The quote is also unsupported; validation stopped at the class error.
- The response recorded 192 prompt tokens and 34 completion tokens. The exact received-byte SHA-256 was `7f08843753cbda5920e563763e2b2f3aae32fbbda25f6db19a61d4124f004b9d`; decoding retained base64 and recomputing SHA-256 matched. Failed status and exact response bytes survived closing/reopening the dataset. The raw envelope identifies the actual model path; the normalized `reported_model` field remains null when validation fails before that field is populated.
- A second request asking for ten candidates was cancelled while `generating`. Tuldok reached `cancelled`, its worker stopped in 0.032 seconds, and it admitted zero candidates. This qualifies Tuldok's local socket/worker cancellation; it does not independently establish the exact instant backend inference stopped.
- The owned runtime received SIGINT and logged shutdown at 23:42:10 UTC. A subsequent exact process-name check found no `pumas-rpc` or `llama-server` process remaining.

## Acceptance limits

Real discovery, chat transport, correct rejection, exact failed-response provenance, reopening, and active-request cancellation were exercised. Real valid-candidate draft admission and semantic quality remain **unqualified** because this tiny model did not produce a valid proposal. Controlled-provider tests continue to cover admission and human-reviewed release; they are not real-model quality evidence. No validation was weakened and no larger model was downloaded.
