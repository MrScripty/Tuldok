# Pinned producer gateway qualification

Producer: public Pumas-Library PR54, exact commit `40c5cbfed67a6f0e862a1197bb5105363d67bdb1`, including PR53 `f3b3c770ca531f013c8e1f8b1f958b9dc0babbfb`. These files are authored qualification glue, not producer code or real-model evidence.

`qualification_gateway.rs` is a normal, non-test binary. Copy it to `rust/crates/pumas-rpc/src/bin/qualification_gateway.rs`; create `rust/crates/pumas-rpc/src/s3.rs` as a symlink to `contract/s3.rs` for Rust's nested module resolution in this added composition. No pinned file changes. Build with default features: `cargo build -p pumas-rpc --locked --offline --bin qualification_gateway`.

The binary calls the unmodified production `server::start_server`, handlers, admission, and `http_transport`. Its Pumas API disables the HF client and enables the process manager. Text uses an external controlled HTTP backend. Image uses the existing managed Torch launch strategy with this authored `serve.py` and a `venv/bin/python` symlink to the installed Python interpreter; it does not install Torch or load any model. The worker emits literal PNG pixels and source-derived protocol-3/slot metadata. A positive result establishes gateway compatibility checks, projection, and actual process custody, not a qualified model or inference runtime.

Run directories contain:

- `gateway.json`: actual gateway/worker URLs, served aliases and exact profiles, owned managed-process observation, PID and listener proof.
- `text-worker/control.json` and `controlled-image-worker/control.json`: operator-selected controlled responses. Set `text_response` to an exact annotation JSON string. `text_mode`/`image_mode` supports `success`, `hold`, `transport_loss`, `provider_failure`, and `malformed`; text additionally supports `truncated_stream`. Optional `text_delay`/`image_delay` holds a finite response before headers.
- Each worker's `requests.jsonl`: exact request JSON and bytes, including observed disconnects. Do not change controls concurrently with a test.
- `producer-qualification.json`: finite typed text/image, live protocol drift, unsupported vision/audio/options, real SSE completion/truncation, unknown transport loss and original backend disconnect checks. `probe_gateway.py` runs those checks against the existing process.

Request IDs are correlation, not provider idempotency. Neither worker nor gateway probe retries admitted requests. No text seed or JSON-format option is sent. The finite consumer UI does not claim streaming UI support; the separate probe tests actual producer streaming.

For orderly teardown, create `stop` in the gateway run root. The binary awaits the production server's shutdown and records `shutdown.json`. The external text worker remains owned by its launcher and must be explicitly terminated after consumer qualification; a disconnect notification alone is not proof of provider cessation.
