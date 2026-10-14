# Boundary investigation and test design

Preparatory evidence for main `f7543fb78f6f1cb52e45dd315efa17a4b2fe6fa6`.
Read the full Tuldok #59 and Coding-Standards #3 issue bodies and all comments
(none at intake). No qualified #3 implementation has been supplied. This is a
Tuldok seam inventory and acceptance design, not a finished telemetry contract.

## Actual owners and seams

| Owner / location | Actual observation | Adaptation constraint |
| --- | --- | --- |
| `mcp_stdio.py:reader` byte buffer | Complete newline frame length, malformed frame, oversize, incomplete EOF | Observe before decoding; do not queue raw bytes; an incomplete EOF frame is a framing observation, not an admitted tool call |
| `parse_frame` | Duplicate keys, invalid UTF-8/nonfinite/surrogate/NUL/depth/object bounds | Record a closed framing category, never exception input or frame |
| `Profile.accept` | JSON-RPC/version/ID/method/state/extra-field/name/argument-shape refusal, ignored notifications, busy/duplicate refusal | This precedes SDK callbacks; instrumenting only `call_tool` misses it |
| SDK request model validation in reader | Invalid method-specific parameters | Separate this validation refusal from dispatch/domain failure |
| `agent_api.validate_arguments` in reader | Registry/schema/aggregate import/sequence refusals | No client call occurs; do not attribute a domain outcome |
| `Profile.admitted` and zero-capacity incoming channel | One pending admitted request, initialized notification transition | Preserve current overlap refusal/serial execution and notification behavior |
| SDK `list_tools` and `call_tool` callbacks | Discovery; validation; actual `AgentClient.call` thread dispatch; output validation; bounded typed errors | Callback begin/end and dispatch markers belong to the same admitted interaction |
| `write` final encode/fallback | Final encoded JSON-line length; oversized response substitution | Count the actual substituted response bytes and retain delivery classification separately from domain return |
| `write` under output lock | Per-write byte progress, whole-line completion, timeout/broken pipe | Whole `os.write` loop completion establishes kernel pipe acceptance only; it does not prove client consumption |
| `Profile.replied` | Pending request released only after SDK response write | Do not let direct refusals clear or finish the original admitted interaction |
| `serve` finally / process termination | Normal exit, cancellation, disconnect, abrupt disappearance | Preserve unfinished durable evidence; no guessed success or cross-session repair of live records |
| `main` optional imports/config/bootstrap | Startup before protocol session | Bootstrap is separate from MCP interactions; no credentials/endpoints/config paths in observer diagnostics |

`agent_api.py` remains the stdlib-only registry and authenticated local HTTP
client; no new observer path belongs there. HTTP/domain owners retain grants,
authorization, commits, retries and audit custody. `AgentAPIError` carries a
bounded public code/status/message for agent output; public error text is still
not an observer allowlist. Unknown domain codes cannot be persisted verbatim.

Current bridge limits are input 1 MiB, output 32 MiB, depth 64, stdout write
deadline 5 seconds, and serial admitted dispatch. HTTP defaults/deadlines remain
owned by AgentClient. Telemetry may not alter these limits or keep output locks
while waiting on storage. Notifications are not response-bearing requests;
decide their explicitly labelled representation from the qualified reference.

## Correlation/privacy traps

- Never use arbitrary JSON-RPC string IDs as stored identities or hashes.
  They can contain a credential/path and are reused legally after completion.
- A duplicate pending ID returns a direct `id:null` error while the original
  keeps running. A busy refusal with another ID is also a distinct observation.
  SDK output ID lookup alone cannot identify every interaction.
- Unknown method/tool names, `_meta`, clientInfo names/versions, custom/dynamic
  argument keys, URL queries, filenames and HTTP error messages can carry secrets.
  Lookup known public vocabulary; otherwise store fixed unknown/redacted categories.
- Structural summary must inspect only declared literal parameter names and
  types/size bounds. No arbitrary recursion into annotation/recipe/asset bodies,
  user object keys, value-derived hashes, domain IDs or source digests.
- Public registry/schema/implementation fingerprints are code identity; content,
  artifact, material, request and token hashes are sensitive and excluded.
- Continuation tracking, if supported, must avoid raw domain identifiers and
  guessable hashes. No continuation metadata exists in today's MCP profile that
  justifies inventing an agent task chain.
- No stdout diagnostics. Storage exceptions must never stringify paths, SQL
  bound values, request data or arbitrary exception text to stderr.
- Secure file mode is an operator control, not isolation from same-user programs.
  Validate the configured directory/file and SQLite sidecars; do not chmod or
  replace unrelated existing files to manufacture safety.

## Direct acceptance scenarios after reference admission

Use existing `SDKProcessTests` process helpers rather than a second MCP protocol.
Extend test-only child configuration to enable an observer on temporary private
storage. Construct identical deterministic cold sessions with enabled/disabled
observers. Read actual stdout bytes and independent SQLite rows after close.
Include initialize, initialized notification, tools/list, context_get and ping;
assert order, cardinality, known identities, elapsed nonnegative duration and
exact observed input/final-output byte counts. Compare public output and the
base registry/tool fingerprints in [baseline](baseline.md).

Also launch the actual `mcp_stdio.py --config` production entrypoint with a private
temporary AgentClient config/token and a real local HTTP bootstrap fixture.
Authored `serve()` children bypass main/config/bootstrap and cannot qualify
operator activation. Prove default-disabled creates no store/sidecars or observer
worker, explicit enablement persists, explicit disablement stops collection, and
invalid/unavailable observer configuration reports bounded sanitized operator
health under the admitted fail-open policy. Verify health/readback and safe
rotation/retention controls outside the MCP catalog. Do not choose their final
CLI/config shape until the qualified reference is available.

For each refusal, start from a valid initialized session and change one condition:
invalid JSON/duplicate member/nonfinite/UTF-8, incomplete EOF, overlong line,
unknown method, malformed known method parameters, unknown tool, wrong argument
kind, known-tool schema error, busy overlap and duplicate pending ID. Assert the
specific existing JSON-RPC error, absence of dispatch, one distinct interaction,
and original pending call remains live. Reuse a completed request ID and assert
two generated correlations. Do not treat notifications as unanswered requests.

Typed execution cases must distinguish schema rejection, authentication/permission
401/403, actual domain 4xx/5xx, registry mismatch, HTTP transport/deadline failures,
output-schema error, bridge exception, response-too-large substitution, and
successful mutation. Authored clients prove bridge mapping only. For authority
and mutation, extend real `AgentHTTPCase`/workflow fixtures: issue an inspect-only
agent through the owner, attempt an edit for a real refusal, issue scoped edit,
make one draft mutation and compare domain revision/audit and response envelopes.
Do not expose observer tools or retry a mutation.

For interruption use a child that signals dispatch entry, then block its authored
client and independently read back a committed begin before terminate/SIGKILL and
reopen in another process. Dispatch entry alone cannot prove durability when the
reference uses a queue. A separate kill-before-commit case must describe possible
observation loss under the admitted fail-open durability contract; missing begin
evidence is not itself corruption. Durable begin evidence must remain
unknown/incomplete, never completed. Separately
prove that killing one bridge while another session is live does not rewrite the
live session. For lost delivery, close the output reader after observed dispatch
and test a bounded actual partial write/timeout. Retain completed domain evidence
separately from unacknowledged delivery; no rollback or automatic retry.

Storage tests use actual SQLite: independent exclusive lock, inaccessible/missing
private directory, page-count exhaustion, two sessions with unique chronology,
reopen/readback, queue/write-budget saturation, bounded shutdown, maintenance
while active if supported, retention over row/time/size limits, initial-version
creation, supported migration if any, unsupported version, foreign database,
truncated/corrupt database and malformed records. Unsupported/corrupt state stays
intact for operator recovery. No destructive automatic rebuild. Check operator
health and unchanged MCP results in every failure case. Decide recovery/rotation
preconditions and guarantees only after inspecting the reference.

Privacy cases put unique sentinels in credentials/config paths, JSON-RPC IDs,
unknown method/tool names, arbitrary keys, source text, base64 bytes, annotations,
recipe prompts, `_meta`, continuation/domain IDs, URL queries, domain errors and
outputs. Search raw SQLite pages and WAL/journal/sidecars plus stderr/health output
for sentinels and sensitive-content hashes. Include invalid/pre-dispatch inputs,
exceptions and post-retention state. Summary size/shape assertions independently
validate closed vocabulary and bound dimensions. No real sensitive records.

Finally run current `test_agent_*.py`, MCP, artifact segment, scoped access,
approval/external-run and generic project execution tests against disposable
PostgreSQL with official pinned SDK dependencies. Baseline failures must name
whether execution reaches the changed boundary. Independent GPT-6.1 Sol High
review must examine actual source, privacy, fail-open and lifecycle composition;
preparatory review cannot qualify an implementation that does not exist.
