# Owner phase timing v1

This source-core slice adds bounded diagnostic observations from the existing
Pipeline, Runs and sealed custodian owners. Timing does not authorize admission,
GO, cancellation, custody, recovery, publication, reservation, result reads or
scientific acceptance. It does not change an existing Run outcome or replay work.
The existing Run panel and browser timing acceptance are separate work.

Selected-v1 `graphs.preparation_timings` posts an exact `graph_id` and `revision`
to `/api/workspace/graphs/{graph_id}/preparation-timings`. With current inspect
authority it returns the current actor's latest volatile observation for that
exact graph/revision, including preparation/capture before a Run exists. Reads
never start preparation. Another actor, an evicted observation, or a cold reopen
has unknown granularity. A changed graph revision refuses the old selection.
Up to 64 actor/graph/revision histories are held in process memory; a newer
concurrent preparation for the same identity is the latest observation. These
histories do not supply a durable submission receipt or an execution request key.
The closed selection label is `latest_actor_graph_revision_observation`. Nullable
`observation` names the exact operation (`graphs.preflight_external` or
`graphs.capture_external`), its clock ID (equal to the sole returned pipeline
clock), and material SHA256 once the owner knows it. Material is null before
preparation returns. A later failure can retain a known digest with incomplete
spans; it does not imply successful preflight. An older in-flight reply never
replaces a newer observation. Another same-actor tab can replace this latest
observation. Graph/revision alone therefore cannot correlate these diagnostics
with a specific successful preflight reply. Consumers must match the exact
operation/material/clock selection and still use the original preflight result
for its own validity; the old preflight projections do not gain a clock field.

Selected-v1 `runs.phase_timings` gets
`/api/workspace/runs/{run_id}/phase-timings`. Current inspect and transitive input
authority are required. It returns the exact catalog, Run and original saved
state, evidence availability and at most four owner records. The existing Run,
progress, preflight, publication, custody receipt and legacy discovery projections
retain their previous shapes. Every complete contract present at source
`5a1feac9f27e23e471c6b57d1f74c026c01c3dd6` is frozen by an exact canonical
full-document SHA256 manifest, including prose and schemas (120 contracts).
The standalone consumer imports no application, database or execution owner.

Each record has its own random clock ID and owner (`pipeline`, `runs`, or
`custodian`), UTC observation label in epoch milliseconds, dropped-span count,
and at most 32 spans. Each span carries an owner-local sequence, phase,
`open`, `measured`, or `incomplete` state, monotonic start offset, optional end
offset, elapsed observation and optional bounded wait reason. Offsets are relative
to that clock's creation. UTC labels are not duration inputs. Different clocks
cannot be subtracted, and overlapping spans must not be summed. Millisecond
resolution may give a zero duration for a short observed interval. Measured
intervals satisfy end minus start equals elapsed. An incomplete interval has no
claimed end; its elapsed value is only the observed prefix. Open means the owner
reported the span open at the observation label, not a liveness or progress proof.

Pipeline records fresh external material preparation and capture, with no timing
field inside hashed material or preflight reports. Capture observations attach to
the admitted Run only after the normal authority/material/capacity boundaries.
Runs records the original queue interval, capacity wait observations, actual
catalog acquisition around executor dispatch, parent launch verification, output
validation and original publication. The sealed custodian separately records its
preparation, wait for GO, runtime verification, observed leader lifetime and
descendant drainage. Leader lifetime includes the launched process's preparation,
I/O and work; it is not optimizer/compute time. No scientific or performance
claim follows from it. Publication continuation records source verification and
copy intervals in the same Runs owner; its original failed/interrupted label and
continuation receipts remain unchanged. A measured copy interval does not prove
that subsequent result attachment or its commit acknowledgement succeeded.
Uninstrumented builtin phases and historical spans remain unknown; the real
external path is the first detailed source-core coverage.

Optional Run timing metadata uses the existing Run document and acknowledged
state saves. It adds no SQL migration, timing-only commit, reservation, grant or
audit authority. Custodian timing uses a separate private bounded 16 KiB diagnostic
file in the anchored custody directory, with its attempt/request/spec identity.
It does not extend the frozen receipt or control packet grammar. Transition
writes use exclusive temporary files and atomic replacement; the final optional
sample syncs file/directory. Missing/corrupt/foreign diagnostics give partial or
unavailable timing, without invalidating valid custody or published artifacts.
The existing 256 KiB custody metadata allowance covers this diagnostic file.
Stopped backups already retain Run documents and the existing external custody
directory. Timing is optional evidence, not an additional restore prerequisite.

Owner history is capped at 32 spans per clock (old closed spans are evicted with
an explicit count), four retained records/32 KiB per Run, and 64 in-memory Run
clocks. Open observations have a seven-day offset ceiling; exceeding it yields
incomplete timing rather than an invented duration. After cold reopen or loss of
a live owner clock, saved open spans become incomplete and are never advanced
using wall time. A custodian sample from another process is never extrapolated.

Timing-domain catalog access uses the existing five-second bounded command policy
and rechecks current authority before disclosure. A peer advisory-lock holder
causes a prompt typed refusal. Initial HTTP authentication, local filesystem I/O
and OS scheduling retain their existing independent bounds. Original publication
holds the existing catalog transaction: a concurrent timing read may be unavailable
until that boundary releases. There is no stale-authority bypass or second
telemetry/authentication service to make that interval live. The owner-recorded
span remains inspectable afterward. Full live-browser T4/T8 acceptance is pending.

The existing CLI adds `phase-timings --run-id ID` and
`preparation-timings --graph-id ID --revision N`, through negotiated exact selected
operations. Both are reads. Consumers reject malformed/contradictory spans and
wrong catalog/Run/graph/revision responses without retrying a mutation.
Qualification uses controlled monotonic clocks and fresh disposable PostgreSQL17,
real neutral process custody, queue capacity, catalog mutex/advisory waits,
cancellation, publication fault/recovery, HTTP and CLI. Neutral fixtures make no
training, CUDA, numerical producer or scientific claim.

## Existing Pipeline and Runs views

The existing Pipeline panel reads the selected saved external graph's latest
actor/revision observation, including while real preflight is running before a
Run exists. It shows the observed operation and nullable material digest and
explicitly labels replacement by another same-actor tab. This projection never
satisfies material approval or establishes successful preflight.

The existing Runs detail displays a table per owner clock with phase, state,
observed milliseconds, current observed wait and start/end offsets. UTC observation
labels, omitted-span counts, incomplete prefixes, unknown historical granularity
and unavailable reads remain explicit. Values are never extrapolated or summed;
leader lifetime is a process interval, not an optimizer measurement. Recovery
publication spans appear on the original Run without changing its saved outcome.

Both read paths pin their complete selected contracts and validate closed shape,
owner/phase, catalog/actor/selection, clock uniqueness and interval consistency.
One sequential read per view has a ten-second client wait and bounded response;
a refresh window performs at most30 reads over at most75 seconds, with a two-second
delay between completed requests. A user can explicitly start another window.
There is no mutation retry. Navigation, graph edits/selections and session changes
abort the current client wait, clear timers and fence stale delivery. Authorization
refusals stop automatic timing reads. Aborting a read cannot cancel admitted work.

The UI admission includes the new static timing module and its single existing
application static-file route, focused controller/pin tests, a neutral browser
fixture and the existing CI workflow. No Python domain authority, operation
schema, persisted clock or lifecycle transition changes in this UI slice. Browser
qualification exercises actual preparation, capacity queue, a separate-thread
catalog mutex wait, one explicit cancel/drain and an original publication fault
followed by same-attempt recovery. It is neutral CPU process evidence; no model
training, CUDA, optimizer or scientific performance claim is made.
