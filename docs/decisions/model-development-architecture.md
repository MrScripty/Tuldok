# Model development: immutable trial material and task-owned evidence

Status: selected architecture design, 2026-10-15; product implementation and
qualification pending. This decision records the design outcome of the
[end-to-end model-development plan](../plans/end-to-end-model-development/plan.md).
It grants no training, migration, telemetry activation or deployment authority.

Tuldok's requested workflow connects data creation/annotation/review/freeze,
model authoring, training/evaluation, correction/tuning and candidate export.
Existing Releases, Pipeline, Runs, RuntimeSnapshots and Access already contain
data lineage, editable recipe and execution/custody/authorization responsibilities.
Copying these into an umbrella experiment object would create competing owners.
Current classifier and optional scientific evidence have different numerical
meaning, fitting clocks and retained histories. A generic graph or scalar log
cannot recover missing checkpoint predictions or establish physical quality.

Keep Pipeline as the **single editable recipe authority**. Model definitions own
computation/preprocessing/output policy and immutable source/configuration;
training produces fitted values and weights under Runs custody. Experiments own
finite trial membership, budgets, selection and candidate decisions, referring
to exact immutable Pipeline material. No independently editable study overrides.
Model computation is distinct from the execution workflow.

Begin with supported template forms/typed configuration plus captured project
source. No general editable graph/code round-trip or universal field/operator
schema is required. Input/output fields, stages, shapes, units, gauge and fitted
transform meaning are explicit versioned task/adapter contracts. Changes prepare
new material or return unsupported, even if tensor shape stays unchanged. Optional
Rheon/lab numerical ownership does not move into generic Tuldok.

One Runs custodian admits all training, derivation, evaluation, packaging and
fresh-inference attempts. Finite explicit trials/repeated seeds are the initial
mode; retry is a new attempt, receipt reconciliation is not. Reserve total budgets,
check current authority, consume required exact external grants, and create
Run/continuation/association and required audit in
one outer catalog transaction with Runs-owned outer-commit wake. Stop closes
admission epoch first, then drains/cancels children. Unknown commits/cessation
retain reservations and fence new admission; restart never replays proposals.
Current built-in owner-only starts and external exact actor/material one-use
grants remain. Budgets are admission/accounting, not absent OS CPU/GPU/RSS quotas.

Supported adapters automatically emit bounded checkpoint/probe/evaluation evidence;
ordinary users/agents add no callbacks, logger calls or charts. Clock/model-bound
checkpoint descriptors can share identical weight blobs without merging samples.
Task evaluators own metrics/comparison and scientific interpretation; Runs owns
verified bytes/publication. UI and structured bounded queries share the same
snapshots/access. Compact contextual dark panels expose the next decision, with
keyboard/numeric controls and explicit missing/partial/incompatible states.

Clients negotiate exact locally supported per-operation contracts. Additive tools
preserve unrelated compatible operations; incompatible mutations fail before
entry/grant consumption. Retain the bounded f58880df legacy projection for actual
strict clients until an inventory-owned cutover. Current permissions/revisions/
material checks are independent of compatibility. No generic schema-subsumption
engine or downloaded executable routes.

Preserve frozen historical targets and selected-only v1 evidence honestly.
Current data corrections create new revisions/releases/trials, not rewritten
results. New protected scientific modes remain unavailable until every whole/
segment/capture/import/query/summary/cache/export accessor protects mixed artifacts
or producers split them. A UI-only test gate is insufficient. Candidate selection,
package closure, fresh-consumer inference and numerical acceptance are distinct.
Unknown distribution rights deny affected exports; no public license is invented.

Passive observer recording stays operator opt-in, privacy-allowlisted and separate
from mandatory transactional audit and training evidence. Agents manage no
telemetry lifecycle/IDs. Recording failures degrade diagnostics alone; required
audit failures roll back their domain transition. Wider observation needs fresh
operator-selected versioned store and actual boundary/overhead qualification.

Alternatives considered: Experiment-owned compilation replacing editable Pipeline
recipes; universal editable model/workflow graph; external annotation/tracking/
training platform as authority; independent task/candidate/viewer registries or
study supervisor. Existing independent recipe callers, exact access/custody and
two worked semantics favor the selected composition. New model/study/evaluation
responsibilities contain necessary caller work; extra registries/services do not.

The design environment lacks the pinned Torch runtime and recurring producer.
Source bounds, actual array formatting and disposable existing-observer measurements
support only their named claims. New automatic profiles stay unavailable until
real producer capture/time/RSS/cold-inference qualification. Optional scientific
physics remains domain-owned/unqualified; authored fields never close required-real
claims. This bounded unsupported disposition leaves selected ownership/contracts
valid without promising costs or adding runtime installation to ordinary use.

Implementation is dependency-ordered in the [handoff](../plans/end-to-end-model-development/reports/implementation-handoff.md):
compatible operations → immutable material/atomic studies → actual classifier
vertical → optional field/one-fit integrations → package/fresh inference → wider
observation and integrated qualification. It supplies exact proposed write sets,
migration/consumer dispositions and runnable/viewable acceptance checkpoints.
Revisit when actual consumer, numerical semantics, capture cost, permissions or
runtime evidence invalidates these responsibilities. Do not upgrade a design
review or prototype into product acceptance.
