# Optional local MCP observer

The operator may opt into local SQLite observations of the existing MCP stdio
bridge. This is separate from PostgreSQL domain metadata and domain audit records.
It adds no tools, schemas, authority, retries, network exporter, analytics or
reporting surface. Existing installations remain disabled unless their operator
explicitly configures recording. Stdout remains exclusively MCP frames.

## Configure, disable and verify

Use an existing private operator-owned local directory (mode0700), outside tracked
repositories, agent-visible data and artifact directories. Configuration is a
bridge launch option, separate from the unchanged private AgentClient JSON file:

```sh
.venv-agent/bin/python mcp_stdio.py --config /operator/private/agent.json \
  --observe-database /operator/private-observations/mcp.sqlite
```

This is an example for an operator-approved new configuration, not authorization
to activate telemetry on an existing installation. Omit `--observe-database` and
restart the bridge to disable collection. Omission creates no observer store,
worker, queue or background task; retention options alone do not enable it.
After a stopped session, verify persistence without exporting observed metadata:

```sh
python mcp_observer.py --database /operator/private-observations/mcp.sqlite
```

The operator-only JSON contains schema version, store integrity state and retained
start/terminal/unfinished counts. It returns nonzero with a fixed diagnostic for
unavailable/unsafe/corrupt/unsupported storage. It does not expose stored arguments,
identities, operation distributions, timelines or output values. Read-only checks
work alongside writers; offline retention requires no active recorder:

```sh
python mcp_observer.py --database /operator/private-observations/mcp.sqlite --retain
```

This applies the store's existing policy. It never creates a missing database,
changes policy, replaces corrupt state or migrates an unknown store. Stop all
writers before maintenance or rotation. The process lock refuses offline retention
while an observer holds that file. To rotate: stop all bridges, check the store,
preserve a private backup if required, move the complete standalone database to
an operator-chosen private archive location, and start with a fresh absolute path.
Do not move/remove journal sidecars while recovery is pending. A failed check
requires preservation and operator diagnosis, not an automatic rebuild. Never
rename an active database; file locks cannot make that safe. Disposal of the
archive/backup and storage snapshots remains the operator's responsibility.

Options and fixed limits:

| Launch option | Default | Permitted range |
| --- | --- | --- |
| `--observe-max-calls` | 10000 | 16–100000 retained begins across all sessions |
| `--observe-max-age-seconds` | 604800 | 60–31536000 seconds since begin |
| `--observe-max-bytes` | 33554432 | 1048576–1073741824 main SQLite file bytes, page rounded |

Policy is persisted once and must match on every writer. To change policy,
rotate to a fresh store. A mismatch degrades recording without altering the old
store or protocol. Schema limits and exact private-file requirements are not
runtime overrides. SQLite busy timeout is20ms; there are no telemetry retries.

## Privacy and on-disk contract

Schema v1 uses a distinct `TOBS` application ID. It is not compatible with an
Engine observer store or PostgreSQL metadata. All values sent to SQLite belong
to a closed projection:

- `policy`: validated count/age/page budgets.
- `sessions`: generated random session UUID, wall start instant, public registry
  version/digest, protocol version and source implementation digest. The digest
  covers only installed `mcp_stdio.py`, `agent_api.py`, `mcp_observer.py` source;
  it assumes a coherent immutable installation before process startup. It does
  not identify Git state, domain data or hot-reloaded code.
- `interactions`: generated random UUID, session ordinal/time, allowlisted MCP
  method and installed operation IDs, per-operation public input/output schema
  digests, observed frame byte count and bounded argument shape.
- `events`: at most five distinct stages (`validated`, `admitted`, `dispatch`,
  `returned`, `terminal`), wall instant and monotonic elapsed milliseconds, fixed
  outcome class, bounded status/code/byte counts and delivery state.

The shape uses only exact top-level property names from the installed operation
schema. Scalars retain no contents; strings/arrays/objects may include capped
size (at most1MiB), never scalar contents or nested keys. At most64 declared
fields and8192 ASCII JSON bytes are emitted. Unknown fields are counted, their
names discarded. `annotation`, `document`, `files`, `inputs`, `parameters`, `text`,
`image`, `audio`, `data`, `content`, `body`, `prompt`, `source`, `metadata`,
`environment`, `token`, `password`, `secret`, `_meta` become a fixed redacted marker
without traversal. All nested containers are unexamined; no nested schema paths,
validation messages or offending values are retained. Static schema names such
as `manifest_path` are permitted; the path value is never stored or hashed.

Never retained: raw JSON-RPC IDs, clientInfo, `_meta`, tokens, credentials/config
contents, endpoints/URL queries, file paths, images/audio/text/base64, annotations,
recipe/source bytes, prompts, arbitrary results/errors, domain IDs or content/
request/material/artifact hashes. Unknown method/tool names become fixed markers.
No content hashes or structural hashes are produced. Only public code/schema
fingerprints are stored. No legitimate continuation identity exists in the current
bridge profile; no task chain or continuation is inferred from domain IDs.

The existing directory and ancestors must be trusted against replacement for the
whole process lifetime. Final symlinks, hardlinks, non-regular files, non-owner or
group/world-accessible database/sidecars and non-private parent directories are
refused. New databases are0600, journals inherit private access. Local POSIX
SQLite DELETE rollback journals only; WAL/SHM stores are refused. Same-user
filesystem access is **not an isolation or tamper-proof audit guarantee**. The
operator must own encrypted storage, backup access and disposal decisions.

## Lifecycle and evidence meaning

A begin commits before SDK admission/dispatch. Actual framing, protocol profile,
SDK method validation and argument-schema refusals are observed before `call_tool`.
Valid notifications have no response pair and are excluded. Malformed no-ID
messages that receive replies are observed. Generated identities distinguish
reused client IDs and direct duplicate/busy refusals from the original live call.
At most two observations are active: admitted request and direct refusal.

Tool dispatch and return are independent stages. `returned` records a valid
`success`, permission refusal, domain error, transport error, registry refusal,
call error or unexpected bridge error classification; no raw codes/text. HTTP
status is present only when the client returned an envelope from its HTTP path;
transport exceptions have null HTTP status. `envelope_status` also includes
synthesized bridge statuses. AgentClient can fail before returning a received
HTTP response; that underlying status is unavailable here and is never guessed.
These stages do not prove a domain workflow completed or a mutation did not commit.

Terminal evidence follows the final encode/substitution and actual stdout write
loop, outside its output lock. `written` proves all frame bytes were accepted by
the kernel, not client receipt or processing. Failed/partial writes record known
written bytes and `incomplete/unknown`; failure before reaching the writer can
leave byte measurement null. Oversize substitution records its small actual
frame separately from the earlier client return. Elapsed time includes recording
and dispatch/write work after begin; wall clock and monotonic duration are distinct.
Complete newline-frame byte counts include the newline. Bytes are not tokens, billing or model intent.
For overlong unterminated input, request bytes measure only the observed bounded
prefix before the reader stops; they do not claim total client-transmitted bytes.
Partial EOF counts the observed remainder. Integrity checks prove the selected
SQLite/foreign-key/schema contract, not every manually altered row's meaning.

Normal close marks remaining observations incomplete if storage works. SIGKILL
or storage failure can leave unmatched starts: their outcome/delivery remains
unknown. Reopen never fabricates terminals or changes another live session.
Partial journals recover through SQLite. A failed begin may leave no evidence;
this is not an exact census, durable command queue, replay source or retry grant.

Every write owns a bounded `BEGIN IMMEDIATE` transaction. New zero-length v0
files initialize transactionally; exact v1 DDL/application identity and retained
integrity/policy are checked under writer isolation. Prior nonpristine v0,
foreign/partial/future/corrupt stores are preserved and rejected. No downgrade or
other migration is supported; future schema changes need an explicit migration.

Count/age retention runs on each begin and during explicit offline maintenance.
Starts and their stages are pruned together; unreferenced sessions are removed.
Another process may evict a live start; its late stages are dropped without
recreating it or disabling healthy recording. Idle stores do not expire records
until collection/maintenance resumes. Secure deletion applies to observer deletes,
not old backups, journal history, snapshots or device remnants. SQLite reuses free
pages; no VACUUM/shrink/rebuild occurs. Main-file quota excludes rollback journal
(up to roughly another main-file size), SQLite bookkeeping and filesystem overhead;
filesystem quota remains the final resource boundary.

## Fail-open health and recovery

Operator stderr receives bounded fixed-code JSON health at startup, first
recording failure and orderly close: state, reason, starts/terminals/dropped/pruned
counts for that process. Health emission and cleanup guard their own errors; no
paths, SQL, bound values or raw exceptions are printed. A broken health sink may
lose that channel; use independent process supervision. Invalid observer options
produce only a fixed diagnostic and leave protocol operation enabled.

Unavailable, unsafe, locked, full or corrupt storage disables further recorder
writes for the process and reports degraded health. A telemetry failure never
changes an already committed domain result, returns a substitute MCP result,
retries work, or authorizes a new action. Fix storage and restart to resume;
there is no automatic retry/recovery loop.20ms bounds SQLite contention only.
Synchronous filesystem/stderr operations can stall on a stuck filesystem/sink;
no hard end-to-end I/O latency guarantee is claimed.

## Reference and qualification

Adapted under CC0-1.0 from MrScripty/Coding-Standards
`4887b7aff0ba84acd257da081135b7849cc9c79f`, specifically
`tools/standards_engine/standards_engine/interaction_observer.py` and its lifecycle
and privacy tests. Parent admitted its independent local qualification; hosted
CI is pending and it is not described as merged or fully CI-qualified. Tuldok
revalidates framing, registry identity, redaction, status provenance, concurrent
refusal and delivery semantics. Engine reports/analytics, discovery vocabulary
and observer-v3 replay are excluded. [Reference admission](../plans/mcp-observer/reports/reference-admission.md)
and the plan's final verification report own the exact local evidence/limits.

## Shared interface observation v2

P6 adds the explicitly selected `interface_observation_v2` contract. Existing v1
stores, reader defaults and `--observe-database` remain supported unchanged. No
store is upgraded, no installation enables recording automatically, and no agent
operation, argument schema, response or authority changes to enable observation.
Select a **fresh** private absolute database path with `--observe-v2-database` on
`app.py`, `project_cli.py` or `mcp_stdio.py`. The operator must provision the same
private POSIX directory and storage lifecycle described above. Retention options
have the same defaults/ranges; retention options alone never activate recording.
MCP rejects simultaneous v1/v2 selection with a fixed diagnostic and continues
without recording. Invalid optional observer configuration fails open.

```sh
python app.py --observe-v2-database /operator/private-observations/http-v2.sqlite
python project_cli.py --config /operator/private/agent.json \
  --observe-v2-database /operator/private-observations/cli-v2.sqlite \
  call --operation context.get --arguments /operator/private/arguments.json
python mcp_stdio.py --config /operator/private/agent.json \
  --observe-v2-database /operator/private-observations/mcp-v2.sqlite
python mcp_observer.py --database /operator/private-observations/http-v2.sqlite --schema-version 2
```

The separately invoked reader returns only integrity, version and aggregate
start/terminal/unfinished counts. `--retain --schema-version 2` performs offline
retention under the persisted policy and exclusive process lock. Reader version
selection is exact; v1 readers reject v2 and v2 readers reject v1 without changing
bytes. Preserve and rotate a previous store; never replace refused state.

V2 keeps the v1 policy/session/interaction/event tables with exactly these deltas:
`sessions.boundary` is `mcp|http|cli`; `interactions.contract_version` and
`contract_digest` describe the exact **locally known public** selected contract.
Unnegotiated legacy and local aggregate operations have null contract selection.
Input/output schema digests still identify installed schema code. Source closure
identity covers installed `app.py`, `project_cli.py`, `agent_api.py`,
`mcp_stdio.py` and `mcp_observer.py`, never catalog or user material. The existing
`TOBS` application identity remains; `user_version=2` and exact DDL distinguish
stores. HTTP methods are `GET|POST`, CLI methods `call|status|download`, and MCP
methods retain the installed closed list. Other CLI subcommands use `call`.
Unknown routes, names and methods become fixed markers. V2 byte counters permit
up to 1 GiB so existing large HTTP imports/artifact streams are represented;
v1 retains its original 32 MiB status counter bound.

The shared sink projects before any buffering or SQLite binding. It retains no
raw routes/queries/headers, arguments/results, request IDs, actor/catalog/Run IDs,
material/grant/artifact hashes, nested keys or error text. Its active state holds
only generated observation identities and monotonic start instants. It serializes
shared HTTP writer access with one local lock and a cross-thread SQLite connection;
at most 256 starts are active in one v2 process. Capacity drops observation alone.
MCP's admission profile still bounds its actual simultaneous requests/refusals.
No background queue, telemetry worker, retry or network exporter exists.

Witnessed seams have deliberately bounded meanings:

- HTTP begins before route/authentication admission. `validated/admitted/dispatch`
  precede routing to the handler after current authentication/framing checks, and
  after JSON/selected-body validation for POST bodies. They are transport/handler
  admission, not domain transaction admission. Refusals may have no such stages.
  `returned` follows result projection and encoding, before response headers.
  `request_bytes` counts consumed body bytes (zero when no body was consumed),
  excluding request-line and headers. `response_bytes` counts body bytes accepted
  by the actual socket `send` loop, excluding headers. Header-write failure leaves
  byte count unknown; a partial body write retains the known prefix count.
- CLI begins at command entry after argument parsing. For ordinary operation
  calls, AgentClient records validated arguments, selected compatibility and the
  actual dispatch immediately before its HTTP request. Output return and terminal
  stages surround the actual ASCII JSON stdout/stderr write loop; output byte
  counts include the newline. The download wrapper witnesses its own local
  adapter dispatch; verified artifact custody still belongs to the existing
  artifact verifier. A download does not log each artifact segment as another CLI
  interaction. CLI argument-file size is not inferred as transmitted wire bytes;
  request bytes remain zero when that measurement is unavailable.
- MCP keeps its existing request/admission/dispatch/return/final framed-byte seams,
  with v2 public contract selection from the installed negotiated client. Protocol
  refusals and framing errors remain independently observable without raw IDs.

A successful terminal means all measured output bytes were accepted by the local
kernel/stream, never client receipt, a domain commit, Run completion or model
quality. An exception before output, partial write, process death or storage
failure can leave incomplete or unmatched starts. Orderly recorder close records
unknown/incomplete terminals where storage permits. Reopen does not complete old
starts. A broken health stream is guarded independently of domain results.
Required Access/Run/exposure audit remains under its existing transaction owner;
passive recording cannot replace it, trigger a retry or roll back its result.
Authoritative lifecycle inspection remains separately authorized Runs/study reads,
without copying protected identities into the passive store.

`tests/test_interface_observation.py` exercises actual HTTP handlers, AgentClient,
CLI output and real MCP SDK processes with authored domain owners, storage failure
matrices, privacy, retention and delivery failures. Existing authenticated domain
HTTP/CLI tests separately qualify ordinary behavior. These transport observations
do not replace H1–H7 model workflow acceptance or required transactional-audit tests.
Local overhead measurements are reported with their exact environment in the P6
qualification report; no complete census or zero-latency guarantee is made.

## Bounded MCP output buffering

The MCP writer requests up to 1 MiB capacity for its owned stdout FIFO when the
host supports `F_GETPIPE_SZ/F_SETPIPE_SZ`. This avoids premature backpressure on
the already supported 8 MiB artifact segment's duplicated JSON text/structured
frame while the official SDK assembles a newline. One active SDK request and the
existing output lock retain one active writer. The request adds at most 960 KiB
capacity over the qualified host's 64 KiB pipe; kernel page allocation is demand
based. An inherited larger pipe is preserved, not enlarged again. No global OS
setting or installed SDK code changes.

Unsupported or refused resizing leaves the inherited pipe and ordinary writer
behavior. The five-second write deadline, 32 MiB frame bound, byte counts and
unknown/incomplete terminal on stalled or broken delivery remain unchanged.
Capacity is a bounded local resource, not a client-receipt or throughput guarantee.
This wire-compatible change applies to both recorder versions and disabled
recording; optional telemetry is not responsible for making a transfer succeed.


Configured CLI observation keeps stdout and its single JSON stderr diagnostic
reserved for the ordinary command contract, including unavailable storage and
invalid observer policy. CLI recorder health emission is quiet by default; use
the separately invoked operator reader for store integrity/retention inspection.
The reader does not prove a particular process recorded every call. An embedding
operator may supply a separate diagnostics stream at composition. HTTP/MCP retain
their existing operator stderr health channel. No domain error payload gains
observation fields, extra stderr documents or a substitute result.
