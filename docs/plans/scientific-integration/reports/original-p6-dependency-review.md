# P6 dependency and protocol boundary decision

2026-10-13; dependency decision followed by admitted isolated source preparation.
No packages installed, model executed or active P5c source changed.
Source preparation is confined to the separately admitted P6 worktree; real workflow qualification still
waits for P5c gates. This records the implementation-versus-adoption decision
required by adopted Coding-Standards/topics/dependencies.md.

## Requirement and selected candidate

Consumer: optional local agent bridge, not app server, catalog readers, native
recipes or captured scientific runtime. Required surface: MCP stdio tools over
one existing authenticated loopback HTTP server; bounded framing/transport;
2025-06-18 tool/lifecycle interoperability; published JSON Schema input/output
contracts; existing owner permissions and durable idempotency unchanged.

Select the official Python MCP SDK **mcp==1.30.0**, using its low-level server and
types, with **jsonschema==4.26.0**, using Draft202012Validator. These are concrete
candidate pins accepted for implementation dependency declaration, not a claim
of installed or security-qualified artifacts. Full resolver/hash closure and
consumer tests must succeed before calling the optional bridge available.

Official source facts:
- MCP1.30.0 requires Python>=3.10, MIT license, and its supported-version list
  explicitly includes2025-06-18. The SDK provides typed messages, server/session,
  request/result handling, schema integration and official client interoperability.
- jsonschema4.26.0 requires Python>=3.10, MIT license. Its declared dependencies are
  attrs, jsonschema-specifications, referencing and rpds-py. Use explicit2020-12
  dialect, not whichever draft a future default picks. Format extras are unused.
- MCP pulls a broader closure including anyio, httpx/httpx-sse, pydantic/settings,
  starlette, multipart/SSE, uvicorn and pyjwt/crypto. We do not enable its HTTP/SSE,
  OAuth, tasks, sampling or network server APIs. Unused imported dependency surface
  still belongs in resolution/vulnerability review; transitive count alone is not
  a reason to replace standardized semantics locally.
- Current base app interpreter has none of mcp,jsonschema,pydantic,anyio installed.
  The proposed dependency is genuinely optional, not ambient availability.

Primary source links (inspected read-only):
- https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/v1.30.0/pyproject.toml
- https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/v1.30.0/src/mcp/shared/version.py
- https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/v1.30.0/src/mcp/server/session.py
- https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/v1.30.0/src/mcp/server/stdio.py
- https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/v1.30.0/src/mcp/server/lowlevel/server.py
- https://raw.githubusercontent.com/python-jsonschema/jsonschema/v4.26.0/pyproject.toml
- https://python-jsonschema.readthedocs.io/en/stable/validate/
- https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle
- https://modelcontextprotocol.io/specification/2025-06-18/server/tools

## Comparison against local protocol/schema implementation

| Requirement | Official SDK + jsonschema | Local MCP subset + custom schema verifier |
| --- | --- | --- |
| Message types/structured results | Existing versioned implementations, official clients/tests | Project maintains unions, IDs, errors and extension behavior |
| Initialization/notifications | SDK behavior inspectable and interoperability-testable; narrow profile adapter still needed | Entire state machine and version-negotiation compatibility owned locally |
| Schema semantics | Established draft validator, schema self-checking, reference handling | oneOf/required/additionalProperties/numeric/string semantics and future drift become local obligations |
| Tuldok-specific limits/auth | Still local: strict JSON/framing, no redirects, credentials, HTTP deadlines, registry parity | Same local obligations; removing SDK does not remove these |
| Packaging/security | Optional dependency lock, upstream advisories, update testing, no app import cost | No package closure, but local protocol bugs/security updates have no upstream implementation fix |
| Maintenance and claim scope | SDK pin + narrow bounded adaptation tests; no general protocol reimplementation | Continuing independent conformance work for every claimed behavior/draft keyword |

Choose SDK/schema implementation because they own difficult standard semantics,
not because of popularity or line counts. The remaining local framing/profile
adapter is explicit and reviewed. Reconsider selection if adaptation would need
SDK private session monkeypatches or copying its main request dispatcher. Do not
silently fall back to a local protocol engine when a package or API is blocked.

## Exact optional declaration and environment proposal

Create optional `requirements-agent.txt` with these direct constraints:

```
mcp==1.30.0
jsonschema==4.26.0
```

Keep it outside base requirements and scientific training/runtime declarations.
If repository convention supports generated lock files, use
`requirements-agent.lock` for the full resolver-produced transitive versions and
SHA256 hashes, recording exact interpreter/platform/resolver command and source
index. Do not invent transitive pins from guessed current releases. The input
file owns the two direct requirements; the lock is generated resolution evidence,
not another manually maintained authority. Installation uses that lock with
`--require-hashes`, after explicit resolution/provisioning admission. If source
preparation precedes resolution, describe dependency satisfaction as pending.

Use a task-owned isolated QA virtualenv in the P6 worktree or explicit scratch
path, from the existing supported host Python. No modification of the base app
venv, trainingvenv, captured runtime snapshot or global site packages. No startup
pip calls, auto-install fallbacks or shell/provider discovery from bridge code.
A missing optional dependency produces a concise setup error without token or
traceback exposure. Separate pure app/registry tests must pass with imports of
mcp/jsonschema/pydantic/anyio blocked. Optional SDK tests require the explicit QA
interpreter and fail setup clearly; they must not count skipped tests as P6 proof.

Before install: resolve all package versions/hashes, inspect source provenance,
licenses, available wheel/platform compatibility and relevant advisories. Record
why accepted. Updates are explicit pin/lock changes owned by P6 maintainer and
must rerun real SDK client lifecycle, schema corpus and HTTP parity/denial tests.
Removal is possible by deleting optional bridge/declaration only; app API keeps
its independent owner behavior and stdlib discovery.

## Import ownership and schema authority

`agent_api.py` registry and authenticated app discovery MUST remain stdlib-only at
import. It contains versioned bounded transport declarations, path projections
and metadata; it must not import optional SDK/schema packages or instantiate
Dataset/domain owners. Registry scope annotations are descriptive, not new auth.
The existing server continues canonical body/scientific/revision/access checks.

Bridge/client validation lazily imports jsonschema in its optional boundary.
Publish `$schema: https://json-schema.org/draft/2020-12/schema` on each schema;
instantiate/check Draft202012Validator for all input/output schemas at bridge
startup. Use self-contained schemas or explicitly supplied in-memory $defs;
reject external $ref/$dynamicRef URIs at registry lint time and configure a
retrieval callback that always refuses network/filesystem resolution. No format
extras: express bounded identifiers with type/pattern/length, not assumed format
validation. Unknown schema dialect/keyword dependence is an admission failure,
not an ignored custom-validator branch. Meta-schema checking is not enough:
positive/negative request fixtures must demonstrate each used construct.

Avoid a second registry of domain semantic constraints. Source-derived transport
shapes describe fields/representation; parity tests call actual owner routes for
all advertised12 task annotations and native import variants. If a shared owner
constant can be projected without dragging server imports into the bridge,
extract a small pure contract constant only with owner approval. Do not broadly
refactor validators to suit MCP. Registry version plus canonicalSHA are published
by HTTP; bridge startup compares expected local version/hash after identity and
catalog checks and refuses mismatch before any mutation. Never negotiate a
silently reduced mutation surface on mismatch.

## Pinned protocol and bounded SDK adaptation

SDK1.30.0 supports more versions than this product initially advertises. Its
ServerSession responds with a requested supported version, else SDK latest; there
is no public per-Server supported-version constructor in the inspected path.
Do NOT patch SDK globals or its private session method. Use the low-level Server
with standard public memory streams and an explicit transport profile adapter.

At the bounded input stream edge, retain the original requested version for
negotiation diagnostics, normalize ONLY initialize.params.protocolVersion to the
single supported2025-06-18 value passed to SDK. The SDK therefore returns2025-06-18
using its normal initialization response. This is the product's explicit narrow
version-selection policy, not a claim it supports the client's rejected version.
The client's initialized notification accepts the offered version; an incompatible
client must close. Do not rewrite other capabilities/arguments/IDs. Test requested
2025-06-18, an SDK-supported older version, and unknown/newer version, all yielding
the truthful single offered version. This small adaptation must be recorded and
reviewed; if public-stream integration cannot implement it without duplicating
SDK session internals, stop and revise the version policy rather than monkeypatch.

SDK default stdio iteration is not the1MiB/depth/duplicate-key/nonfinite boundary.
Implement a bounded strict UTF-8 JSON line transport before constructing SDK
JSONRPCMessage/SessionMessage. It handles maximum bytes/depth/IDs/duplicate keys,
uses bounded memory streams, and emits only complete final capped JSON lines.
Keep transport-level profile states to refuse duplicate initialize, require
notifications/initialized before tools, and handle unknown notifications without
forwarding them into an SDK error/log notification. This is necessary because the
inspected SDK marks initialized after its response, before the client's notice.
Do not register resources/prompts/tasks/logging/progress/sampling handlers or
capabilities; tools and ping are the advertised surface. Unsupported request
methods receive bounded standard protocol errors at this profile boundary.

Tool schemas/dispatch remain the single registry. The SDK call_tool decorator
normally validates schemas and can turn exceptions into text. Prefer explicit
bridge validation with the pinned validator (and SDK validate_input=False) so
error mapping/redaction and reference refusal are controlled consistently. Return
explicit typed CallToolResult only after output-envelope schema validation;
avoid accidental duplicate normalization or raw exception messages. SDK handles
normal message/result serialization and lifecycle; final transport writer checks
encoded total size, including structured+compatibility text duplication.

This adaptation still has conformance/maintenance cost. Required tests include a
real official SDK client plus raw hostile-framing tests, with no supported
capability beyond tools advertised. Do not claim MCP StreamableHTTP support: the
internal existing Tuldok HTTP hop is not an MCP transport.

## HTTP deadlines, serialization and retries

Proposed explicit initial limits: connection timeout5s, per-block socket timeout
min(5s, remaining), absolute complete-call deadline120s, response body16MiB,
request1MiB, final serialized MCP message32MiB. HTTP preflight can scan scientific
inputs/runtime, so5s total would falsely promise availability;120s is a bounded
initial policy needing actual representative preflight measurement. A timeout
fails explicitly and does not cause mutation replay. If measured qualification
needs another value, record that change before release rather than silently
extending time while waiting. Enforce absolute time during header/body reads;
per-read timeouts alone do not stop trickle responses. Reject conflicting length/
transfer encodings, unexpected compression, redirects, truncated body or trailing
framing inconsistency. Read at most cap+1 and never truncate a successful result.

Fixed numeric-loopback endpoint only, direct http.client with no proxy env,
no URL redirection, and validated separately encoded path segments. Credentials
come from explicit private descriptor or bounded owner-only nofollow file.
Startup checks agent kind, configured catalog and registry version/hash. Every
HTTP call still goes through current Access, so revocation remains immediate for
subsequent requests. No credential value, headers or raw exception dump in logs.

One in-flight HTTP tool call; no background mutation queue. Use SDK async
integration with backpressure and finite streams, not blocking the event loop
with an unbounded task backlog. Reject overlapping calls with a bounded busy
result or explicitly serialize admission with no accumulation. Choose/document
one behavior in implementation tests. There is no new arbitrary requests/second
quota or sleep loop: concurrency1, bounded bytes/time and existing Access authority
are the initial load controls. If an actual availability requirement demands a
rate quota, admit it explicitly; do not invent a magic threshold here.

No automatic retry for any mutation, including connection loss,503 storage or
commit_unknown. Agent resubmits exact original request_key/body explicitly to
reconcile existing durable admission. A new retry after failed work requires the
existing approval semantics and a fresh key, preserving failed attempt evidence.
Timeout after bytes were sent is an unknown HTTP acknowledgement, not proof that
no mutation occurred. EOF/cancelled MCP request does not cancel a durable Run;
explicit runs.cancel uses the sole owner. runs.expose_test uses the existing
scope/owner rules, with no invented grant or bypass.

## Remaining gates and ownership

1. Parent records selection/protocol adaptation and optional provisioning admission;
   full transitive lock/provenance/security evidence and actual SDK environment
   consumer tests remain pending. No package installation has happened here.
2. Bridge owner implements SDK stream adapter, optional validation, HTTP client,
   secrets/redaction/bounds and interoperability tests. No custom schema engine.
3. Registry owner produces pure declarations/version/hash/discovery and projection
   corpus for every advertised operation; existing domain owners stay canonical.
4. Runs owner adds stateless bounded artifact segments; unchanged full verified
   download remains available. Segment responses explicitly do not verify the
   whole payload; independent client hashes full reassembly before use.
5. Access/public integration owner qualifies same actor/scopes, forged review,
   holdout exposure denials, grant/revision/idempotency/revocation parity; registry
   metadata never authorizes operations. Include real owner setup via existing UI.
6. CI/docs owner keeps base app dependency-free for agent extras, adds explicit
   optional environment tests, and documents bounded supported matrix/exclusions.
7. P6 completion remains gated on actual preceding milestones and real public
   workflow/SDK conformance, not only source preparation or mocked HTTP fixtures.

## Advisory review and superseded candidate

The initial1.26.0 candidate was rejected before installation after checking the
official repository advisory API on2026-10-13. Select1.30.0 instead: the same
public low-level API, Python>=3.10/MIT, and2025-06-18 support were inspected at
the pinned1.30.0 source tag; both selected distributions exist on PyPI.

Official advisory feed: https://api.github.com/repos/modelcontextprotocol/python-sdk/security-advisories

Relevant published affected ranges include1.26.0:
- GHSA-rwrf-2pqf-9j8j: client tool output-schema remote $ref retrieval; fixed1.30.0.
- GHSA-84m7-p3x7-pcfv: HTTP session retention; fixed1.30.0.
- GHSA-w4fh-qvv9-3v23: HTTP bearer resource audience; fixed1.30.0.
- GHSA-5h93-6whr-6q8j: HTTP redirect header/body leakage; fixed1.30.0.
- GHSA-qx49-fqc8-xw99: OAuth client authorization-server selection; fixed1.30.0.
- GHSA-fmmv-w9g8-j3gc: HTTP/OAuth body bounds; fixed1.29.1.
- GHSA-vj7q-gjh5-988w: WebSocket Host/Origin validation; fixed1.28.1.
- GHSA-hvrp-rf83-w775 and GHSA-jpw9-pfvf-9f58: experimental task isolation
  and HTTP session principal binding; fixed1.27.2.

The feed's remaining older advisories were fixed before1.26.0. None of its
published affected ranges includes1.30.0. This is a bounded advisory review,
not proof of absence of vulnerabilities. HTTP/OAuth/WebSocket/task surfaces stay
disabled; our registry reference refusal stays necessary even with the patch.
The official jsonschema repository advisory feed returned an empty list; this
is likewise limited evidence. Full resolved transitive advisory/license/hash
review remains required before optional QA provisioning.

Base app Python is3.12.14. Its requirements remain Pillow>=10.2,<13 and
psycopg[binary]==3.3.6; the optional bridge never alters these, trainingvenv or
captured runtime. Provisioning and tests remain blocked until the root owner
announces the active benchmark terminal and dependency resolution is reviewed.

## Resolved optional consumer, after benchmark terminal

Root announced the actual P5c benchmark terminal/completed/drained before
provisioning. Resolution used pip25.0.1 and CPython3.12.14 on Linux x86_64,
PyPI, wheels only, in task-owned `.venv-agent`. The exact29-package closure,
wheel URLs/hashes, interpreter/platform metadata, declared licenses and advisory
results are in `p6-agent-dependencies.json`; `requirements-agent.lock` is generated
from that measured closure, not hand-selected transitive guesses. Its wheel hashes
qualify this Linux CPython3.12 target (including manylinux2_34 cryptography), not
unmeasured Windows/macOS/Python versions. Installation uses `--require-hashes`
and `--only-binary=:all:`.

Every selected hash was matched against the exact-version PyPI distribution
metadata. The version-specific PyPI/OSV-derived advisory field returned no known
advisories for all29 selections at this check; this complements the official
MCP/jsonschema advisory review above and is not a universal security guarantee.
Declared licenses are MIT/MIT-0, BSD-3-Clause, Apache-2.0, PSF-2.0, and MPL-2.0
(certifi), with cryptography offering Apache-2.0 OR BSD-3-Clause. This isolated
consumer retains installed package license notices; no modified dependency or
redistributed bundled executable is claimed. Those permissive/file-copyleft
licenses introduce no source change obligation for this separate original bridge;
future redistribution still must retain applicable notices and satisfy each
license. No dependency source was modified.

Base app dependencies are installed separately into this QA environment only for
public HTTP fixture integration. They do not become agent-lock authorities, and
neither the original base environment nor scientific runtime is modified.
