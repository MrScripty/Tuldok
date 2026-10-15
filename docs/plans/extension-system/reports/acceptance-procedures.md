# Extension conformance and independent-author procedures

These are future product procedures for [E1–E4](../plan.md#milestones), not tests
run while authoring the plan. All numerical/execution work needs separate slice
authorization and actual qualified runtime/public-owner fixtures. The plan owns
current acceptance status and exact write sets; this report owns their detailed
case list and A/B fixture subject.

## Mandatory conformance cases

1. Inert listing/open/edit/preflight/history with import-time write, import error,
   `.pth`/startup hook, malicious-looking entrypoint, build hook and missing runtime.
2. Duplicate keys/IDs, conflicting providers, unknown format/required keyword,
   external/cyclic schema references, excessive nesting/count/bytes, nonfinite or
   coerced parameters, path escape, symlink/FIFO and changed root/manifest bytes.
3. Required exact host/semantic/runtime intersections, missing/disabled provider,
   incompatible stage ports and declaration-versus-observation-versus-grant facets.
   Adding an unrelated contribution does not break compatible ordinary operations.
4. Changed source/manifest/model/I/O/stages/runtime/transform/inputs after review;
   stale saved revision, expired/revoked/used grant and wrong actor. Assert no new
   Run/grant/budget change on refusal and one attempt on lost-response reconciliation.
5. Wrong class order/tokenizer, audio sample rate, field axes/centering/grid/units/
   stage/gauge/time or comparison membership. Exact shape alone must not admit it.
6. Missing required evidence, duplicate/late checkpoint IDs, incorrect producing
   clock/probe/weights/fit-member lineage, unsupported output role, undeclared file,
   tamper, NaN metric and omitted optional observation without a reason.
7. Recipe exception/native crash/log flood/malformed progress/hang, TERM refusal,
   detached/double-fork neutral child, controller loss, unknown commit/GO outcome,
   missing drainage and stale success. Use supported neutral custody fixtures;
   do not imply Torch multiprocessing is qualified. No replay/refund/fence bypass.
8. Revoke consuming credential after admission: retained continuation can finish
   its exact effects; new calls/reads require current authority. Explicit Run
   cancel and unconsumed-grant revocation have their distinct tested effects.
9. Object/pickled NPY, malformed shape/header, excessive archive expansion, special/
   symlink output, unsafe checkpoint and incomplete file write. Host does not
   execute extension deserializers while rejecting/inspecting them.
10. Old/new supported client matrix, A/B side-by-side, disable/removal, missing
    current root, backup/restore and original-cache-free consumer. Legacy results
    remain selected-only; absent history is never fabricated.
11. Current authority/exposure parity for view/query/summary/full/segment/capture/
    import/cache/export, including opaque ZIP/NPZ with mixed/unknown holdout data.
12. Unrelated image/text/audio and bounded mesh/point/volume workflows still work
    when field extension is missing, malformed, incompatible or removed. Their
    modality fixtures test the envelope, not new multimodal training integrations.
13. Before any v2 row is registered, verify quiesced pre-v2 backup and declared
    new-binary/store pairing. Demonstrate old saved-row projection on a disposable
    copy as an unsupported counterexample, not compatibility. New host fully
    validates saved v1/v2 rows and refuses v2 through explicit legacy-v1 APIs;
    new browser uses the explicit v2 variant, negotiated agents require P1; rollback restores pre-v2 backup, never silently
    starts an old binary on the v2-written store.

## Concrete A/B extension specification

This is a future worked **CPU scalar-field surrogate** and change-locality test,
not an executed solver or claim of physical qualification. Use tiny explicitly
authored permitted 3D fixtures, with independent equations for expected values;
do not need a live lab/Rheon or code/data generation on opening a project.

Package A contains `project.json`, `manifest.json`, task/model/trainer/evaluator/
view definition JSON, captured numerical `src/`, exact source/runtime requirements,
notices and small train/validation fixture references. Its task binds initial
scalar field, grid geometry/material metadata, target time when actually supplied,
frozen reference target, masks, family/split and train-only fit-statistics lineage.
Pin this worked A/B fixture's inputs, predictions, weights and fitted transforms
to little-endian `<f8>` (the general envelope may separately support `<f4>`),
C-order ZYX, cell geometry,
coordinate frame/units and stage metadata. Do not reinterpret standalone cases as
a physical trajectory. Keep under the selected current profile, not its maximum
just because it exists.

Use an explicitly dimensionless standalone4×4×4 field fixture on a cell-centered
unit-spaced ZYX grid (coordinate units meters; no physical timeline). Version A's
reference mapping is `target = 0.5 * initial + 0.25`. Fit a pointwise affine NumPy
model `prediction = a * normalized_initial + b` using only its frozen training
members. Train-only normalization is retained, with fixed finite update settings
and actual optimizer-update clocks; no claim of heat/diffusion validity follows. A bounded run prepares → fits → infers → evaluates,
retains at least two actual checkpoint/probe observations and outputs exact declared
raw predictions, metrics, checkpoint descriptors/weights and data-only evidence.
Before execution, the independent oracle owner freezes the permitted fixtures,
normalization/direct-weight reconstruction and float64 inference comparison
`abs(actual - expected) <= 1e-10 + 1e-10 * abs(expected)` for each permitted probe.
Expected inference is computed from retained weights/transforms by a separate
small consumer; reference-target errors are independently re-tallied against the
fixture equations. Checkpoint binding and raw/corrected stage identity are required
regardless of numerical quality. This is an acceptance tolerance, not a measured
performance or promised optimizer-convergence threshold. Numerical quality may be diagnostic; fitting this
small mapping does not establish physical diffusion accuracy or generalization.

Package B requires a spatial source field and boundary mask in addition to the
initial field. Its raw reference mapping is `0.5 * initial + 0.25 + 0.2 * source`;
fit a model with both initial and source inputs, then add boundary-enforcement
`corrected = where(boundary_mask, 0, raw)` after raw inference. Input/output units,
mask meaning, fitted transform and raw/corrected stage IDs are explicit. Its output
exposes raw and corrected fields separately and binds exact producing stages.
New task/model/trainer/evaluator versions are used wherever meaning changes, with
new source/reconstruction/material and fresh validation/approval. Boundary policy
is explicit; a corrected metric cannot be labeled raw-model success. Changing
required port or stage must not silently adapt A weights or comparison semantics.

The independent author supplies B only through the documented package seam. Tuldok
application-owner code is frozen for that decisive test. A stays inspectable after
B upgrade/removal, and image/text/audio/Data/Pipeline/Runs remain usable. If B needs
a genuinely new host capability, report the exact unsupported boundary and re-plan
it; do not declare the A/B locality requirement passed with an undisclosed core edit.
