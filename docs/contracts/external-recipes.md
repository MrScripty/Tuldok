# Approved external recipes, version 1

Tuldok can execute explicitly reviewed local recipes through the existing Pipeline
and Runs owners. This is trusted same-user code, not a sandbox: it retains the
operating-system user's filesystem, network and reachable-service authority.
Cleared environment variables, scoped API credentials and closed inherited file
descriptors do not constrain that ambient authority. Approve only code whose
actual effects you trust.

## Definition and graph

A project recipe reference points to bounded `external_recipe_v1` JSON. It names
an exact source closure, an entrypoint, typed parameters, named captured inputs,
a structured argument vector, declared output roles and limits. Opening and
preflight read data only; they never import project code, run discovery hooks or
install dependencies. Unknown fields, unsupported runtimes, escaping paths,
symlinks and changed hashes fail before execution.

The first graph has three editable nodes: input → execute → output. It uses the
existing graph store, revision checks, layout and clone operations. Inputs bind
actual project references or frozen release archives consumed by the recipe.
Changed input bindings or execution parameters require a new preflight; layout
and name remain presentation fields.

The initial `system_python` profile uses `/usr/bin/python3` with `-I -S -B` and a
pinned finite interpreter, standard-library, bytecode and native-library closure.
The installation owner must differ from the app user; files and ancestors cannot
be group/world writable. UID 0 is conventional; this execution container's
read-only installation is mapped to UID 65534. The explicit installed Python
`/etc/pythonX.Y/sitecustomize.py` target is included when referenced. Runtime
immutability is an operational trust assumption, not protection against a host
administrator. Workspace virtualenvs and arbitrary runtime paths are not accepted
by this version. P3b native helper qualification does not silently extend this
public runtime profile.

Sources and input bytes are captured privately. Bounds are 64 source files,
128 captured files, 64 MiB total captures, 32 parameters and inputs, 32 flat output
names, 64 MiB total outputs and 600 seconds execution. Each declared input is at
most 40 MiB. Arguments are separate tokens, never a shell command. No project
environment overrides are accepted; the effective environment is explicit in
material identity. Runtime inventory is bounded separately at 512 MiB. The
separately qualified [captured CPU profile](captured-cpu-runtime.md) permits
256 MiB aggregate inputs and 320 MiB total captures; per-input, source, output
and legacy profile limits remain unchanged.

### Frozen release bindings

Existing project bindings remain exactly `{reference_id, expected_sha256}`;
no default discriminator is inserted into saved graphs or retained receipts.
A frozen archive uses `{kind: "frozen_release", release_id, expected_sha256}`.
The expected digest must equal its content-addressed release ID. Mixed or unknown
fields fail. The release owner captures only its managed archive, under the
catalog lock, without symlinks or caller-supplied paths. It verifies regular-file
ownership, size, stable identity and the exact selected SHA256 before execution.
Frozen bytes remain authoritative after source records change or disappear.

Material retains `{kind, catalog_id, release_id, measured_sha256, bytes}` for a
frozen input and binds the identical private captured bytes. Cross-catalog,
digest and size contradictions fail cold validation. Source meaning, review,
split/family suitability and numerical acceptance belong to the selected reader
and optional recipe; a generic byte capture is not scientific acceptance.

`GET /api/workbench/releases/input-candidates` is inspect-authorized and returns
`{releases: [...]}` with at most 100 managed archive hints. Each contains
`release_id`, expected `sha256`, `bytes` (or null), `status` (`available`,
`unavailable`, `oversize`) and nullable `reason`. Availability checks file shape
and the 40 MiB limit; it does not assert content verification. Preflight captures
and checks the chosen exact bytes. The picker is not another release registry.

## Authority and admission

Preflight returns the material document and its SHA256. The material binds the
catalog, immutable project snapshot, graph execution identity, definition,
source/input bytes, parameters, runtime closure, host/helper code, effective
permissions, environment and limits. Imported host code must match its current
files. Dispatch rechecks the approved host identity; the helper checks captured
and runtime files before READY and again before GO.

An owner approves a specific material digest for one consuming actor for
60–3,600 seconds. The grant is nonsecret. An agent needs live `inspect` and
`execute` scopes plus that explicit grant. Existing classification, generation
and inference paths retain their owner-only execution rules. An owner can create
and consume a grant atomically, but must still submit the exact previously
reviewed digest. Code or input drift cannot silently refresh approval.

Grant consumption, the Run, its bounded continuation and audit are one
PostgreSQL transaction. Grants are one-use; cancellation never refunds them.
Expiry/revocation are checked at consumption. Later cancellation controls already
admitted work. Revoking an approving credential does not retroactively revoke a
durable grant; explicit grant revocation does.

An identical actor/request key/request reconciles the existing attempt even if
the grant later expires. A different actor or request conflicts. A lost commit
acknowledgement preserves captured files and does not make the attempt eligible
for the running queue. Explicit receipt reconciliation may make that same
committed attempt eligible. Restart never automatically replays work. External
retry means a fresh preflight, key and approval, not reuse of the old grant.

## Process custody and recovery

The sole Runs queue starts one pinned single-threaded Linux subreaper helper.
A private bounded socket protocol carries READY, GO, cancellation and custody
receipts; recipe stdout cannot declare completion. The helper and executable
bytes use sealed descriptors. Recipe code receives its own stdin/stdout/stderr,
not the helper's control descriptors.

The helper establishes custody before READY and cannot create recipe children
until GO. Runs commits the exact helper identity and conservative `go_intent`
before sending GO once. Unknown acknowledgement means no GO. A restarted server
never resends it. Controller EOF requests cancellation and drainage.

Cancellation repeatedly identifies direct/adopted children, signals verified
pidfds, reaps them and repeats as descendants become adopted. Detached sessions,
double forks and ignored TERM do not establish escape from this lifecycle.
Only the exclusive helper's `ECHILD`, after spawning closes and streams drain,
proves cessation. Empty process scans and dead leaders do not. Wall time,
bounded diagnostic streams, per-process file limits and output observation are
not aggregate resource or adversarial containment guarantees.

Readiness is bounded at 10 seconds, TERM grace at 3 seconds and cleanup at
10 seconds. The controller independently bounds observation even if the helper
stops running. A missing or invalid drainage receipt after GO intent produces
`unknown` and fences further external execution for that host boot. Merely
acknowledging the error cannot clear the fence. A later valid receipt or a changed
boot ID can prove cessation, never reconstruct successful completion. Legacy
closed CPU-worker recovery remains separate.

## Results and retained evidence

After verified drainage and successful exit, Runs independently checks the
approved output names, roles, required files, sizes and hashes; symlinks, special
files, undeclared names and output drift fail. Captured regular files and custody
and artifact receipts are fsynced before the completed PostgreSQL transition.
A failed/cancelled/unknown attempt exposes no successful result. Ambiguous
publication acknowledgements preserve evidence for reopening.

Every result read checks the retained material/spec, custody receipt and artifact
inventory against the approved contract, then verifies bytes. A changed result
is unavailable rather than silently trusted. Neutral lifecycle tests and native
READY/STOP are labelled as such; neither represents scientific/model acceptance.

## HTTP projection

All routes require the same catalog actor used by domain calls.

- `POST /api/workspace/graphs/external`: name, project and recipe references,
  expected recipe hash, exact named inputs and optional typed parameters.
- `GET /api/workspace/projects/{id}/recipes/{ref}?expected_sha256=...`: declarative
  preview only.
- `POST /api/workspace/graphs/{id}/preflight-external`: `{revision}`.
- `POST /api/workspace/runs/approve-external`: graph ID/revision, expected digest,
  consuming actor ID and optional TTL.
- `POST /api/workspace/runs/submit-external`: request key, graph ID/revision,
  expected digest and optional explicit approval ID.
- `POST /api/access/execution-grants/{id}/revoke`: empty object, owner-only.

Existing Run list/get/cancel/artifact routes serve these attempts. Classification
predictions and test-exposure operations do not apply. Schema 8 adds local grants
and immutable consumption records; explicit quiesced upgrade and versioned
backup/restore retain schemas 1–7.


## Optional native dependencies

An explicit `native_sources` list selects 1–8 paths already declared in `sources`.
A `{native_policy: source_path}` argument refers to host-generated captured JSON.
Omitting native declarations preserves existing definition/material/spec shapes.
The initial policy is `glibc_x86_64_no_preload_v1`: bounded ELF64 little-endian
x86-64 PIE with the qualified interpreter, recursive exact dependencies under
`/usr/lib/x86_64-linux-gnu`, no RPATH/RUNPATH, audit, filter or auxiliary loading.
The material binds loader/library identities and generated policy bytes. The
helper checks the fixed trusted `/etc` directory and absence of any
`/etc/ld.so.preload` entry at launch, READY and GO.

The optional producer verifies and seals native and loader bytes, disables loader
cache and hardware-capability substitutions, and checks actual mapped file
identities before requesting work. This qualifies pinned trusted code; it is not
an arbitrary dynamic-plugin or hostile-administrator sandbox. See the optional
[Rheon producer](rheon-producer.md) for the bounded concrete workflow.

Completed external artifacts can be captured with server-derived custody evidence
for [scientific Data import](scientific-fields.md). Restore preserves the original
absolute execution paths and spec hash as historical declarations. Artifact reads
use the restored catalog's owned paths. Dispatch refuses a staging-path mismatch;
restoration never replays a historical attempt.

## Progress and compact results

`GET /api/workspace/runs/{id}/progress` requires inspect authority and selects
only the existing external Run's owned custody files. It accepts no caller path,
stream or offset. The response contains `schema_version`, `run_id`, `state`,
`custody_phase`, `evidence`, `streams`, `progress` and `result`. Each available
stream has `available_bytes`, `start_byte`, `text` and `truncated`; absent streams
are null. Reads use fixed names, no-follow directory/file descriptors and the
existing 1 MiB stream limit. At most 8 KiB per stream is displayed, with UTF-8
replacement/control sanitization. The whole HTTP-encoded response is bounded to
192 KiB, including JSON escaping.

`evidence` distinguishes `pending`, `live_unverified`, `custody_verified` and
`unavailable`. Active observations are not atomic whole-stream snapshots. Drained
terminal streams require exact custody identity, size and hash checks; completed
streams also bind the published receipt. Missing relocated diagnostics remain
unavailable and never follow historical absolute paths. Cancelled/failed output
can have verified custody without becoming a successful result.

A complete stdout line may use the closed format
`{format:"tuldok_progress_v1", stage, completed, total, metrics}`. Stage and up to
eight metric names are bounded identifiers; counts are integers with
`0 <= completed <= total <= 1000000`, and metrics are finite numbers. Lines over
4096 bytes, incomplete/malformed events and duplicate keys do not become progress.
The latest valid event in the bounded tail is a recipe-authored observation, never
a state transition or proof of scientific correctness. No elapsed-time progress,
epochs or ETA are inferred. Polling reuses the selected Run/session/view guards.

A completed recipe may declare one `result_summary` output, bounded to 64 KiB,
with closed JSON `{format:"tuldok_result_summary_v1", title, metrics, scope,
checkpoint?}`. Title is at most 120 code points; up to 24 distinct numeric metrics
contain `{name,value,unit}` (64/24 code-point name/unit bounds), and up to eight
scope labels have 160 code points each. Strings are plain text, with controls and
surrogates refused. An optional checkpoint names a verified same-Run artifact
with declared `checkpoint` role. No model deserialization occurs in the server.

`result` is null before completion or when no summary is declared. A valid
projection is `{status:"hash_verified", artifact_name, sha256, summary}`;
malformed/tampered summaries return `{status:"unavailable"}`. Verified result
artifacts remain readable even when separate staging diagnostics are unavailable.
The UI labels metrics as recipe-reported, keeps logs/provenance in details and
uses the existing artifact download route. Neither stdout nor a filename suffix
can nominate a result or enable a checkpoint download.

## Completed-Run inputs and optional large CPU outputs

A new exact input binding is `{kind:"run_artifact", run_id, artifact_name,
expected_sha256}`. The existing Runs owner captures only a completed, drained,
same-catalog external artifact, verifies custody and payload bytes, and enforces
the declared input limit before reading. Failed, cancelled or unknown Runs are
ineligible. Its material receipt is `{kind:"run_artifact", source:<existing Run
artifact source receipt>}`; old project and frozen-release receipts are unchanged.
Cold validation reuses the custody owner's source validator without accessing
the original catalog. It checks internal retained relationships, not historical
database authenticity. Editing a binding invalidates material approval.

The optional argument token `{"input_evidence":true}` resolves to captured
`runtime-bootstrap/input-evidence.json`: canonical JSON mapping input slot names
to their exact typed material receipts. The generated bytes are hashed in capture
and recomputed during cold decoding. It carries no credentials or caller-authored
provenance. Definitions without this token gain no capture or identity field.

The explicit optional `resources.profile` value
`captured_cpu_large_outputs_v1` requires runtime `captured_cpu_python_v1`. Its
limits are 2400 wall seconds, 96 flat declared outputs, 512 MiB per file and 4 GiB
aggregate. Definitions still declare smaller per-file/aggregate limits as needed.
The helper's matching `resource_profile` field is accepted only with the verified
CPU descriptor/bootstrap. Old omitted-profile shapes and bounds are unchanged.
Input and source capture limits remain independent and unchanged from P5b.

Output verification and publication hash/copy bounded chunks and preserve the
existing manifest, receipt, fsync and completed-state sequence. Publication does
not rename or delete producer staging. Large downloads use one private anonymous
spool, fully verified before HTTP 200, then bounded transfer; failures/disconnects
close it. Current disk capacity is checked before large admission, publication
and spooling; this is not a filesystem reservation against concurrent writers.

For large-profile Runs only, list/get exposes receipt-verified inventory with
payloads explicitly not checked. Individual downloads/captures verify selected
bytes; full audit verifies every artifact. Small-profile reads keep their existing
whole-inventory verification semantics. A result summary verifies its own bytes
and referenced checkpoint, without certifying unrelated large field artifacts.
The UI labels recorded outputs as verified on download.

Inspect-authorized `GET /api/workspace/run-artifact-inputs` returns at most 100
completed external Runs with candidate artifacts at most 40 MiB. Receipt-verified
metadata is a selection hint; capture remains the byte authority. Closed Run rows
contain run_id, state, status, reason and artifacts. Available artifact rows contain
artifact_name, role, bytes, sha256 and status. Unavailable rows disclose no untrusted
artifact names. No classification holdout or arbitrary filesystem path is exposed.
