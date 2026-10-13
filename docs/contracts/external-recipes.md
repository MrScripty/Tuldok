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
existing graph store, revision checks, layout and clone operations. Inputs are
actual project data references, not invented frozen-release dependencies. A
changed execution parameter requires a new preflight; layout and name remain
presentation fields.

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
material identity. Runtime inventory is bounded separately at 512 MiB.

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
