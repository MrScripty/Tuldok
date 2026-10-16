# Experiment progression

Pipeline’s **Experiment progression** graph shows Trial ancestry across Studies.
Select a card to inspect the authored cohort, hypothesis, intended change, target
metric/direction/threshold and acceptance intent alongside saved Run outcomes.
Solid edges mean derivation; dashed edges mean a comparison baseline. Parent and
baseline identities are also available as text controls. Run retry parents stay
inside their original Trial and never imply experiment derivation.

## Ownership and immutable identity

Experiments owns an optional immutable `trial_lineage_v1` sidecar for each Trial.
A relationship is the exact `{catalog_id, trial_id, material_sha256}` reference,
never a mutable recipe name or latest checkpoint. Parent and baseline may differ;
baselines do not participate in the acyclic derivation relation. All references
must belong to this catalog. A derivation walks at most1,000 ancestors and rejects
cycles or an unavailable depth bound.

Existing Trial v1 documents, material SHA256s and Run custody stay unchanged.
Missing historical ancestry remains unknown. An author may record intent once;
the sidecar states whether it was recorded before admission or retrospectively.
Authored intent does not establish metric qualification, scientific acceptance or
comparison compatibility. Saved outcome summaries are not a new evidence verifier.
Open a Run for its existing verified checkpoint, probe and artifact views.

## Branch, edit, prepare and execute

1. Select a Trial and choose **Branch from Trial**. Declare the intended change,
   cohort, target and baseline. Owners may create a separate closed Study using
   the parent’s exact finite policy and limits.
2. **Open cloned recipe** opens Pipeline’s normal editor. The clone comes from
   the Trial’s retained recipe bytes, even if its original draft has since changed.
   Edit and save the clone. Changing architecture requires a matching published
   Model reference; the optional reference field accepts its ordinary Ref JSON.
3. **Prepare saved revision** captures the saved recipe through existing material
   preparation and atomically attaches the new Trial and immutable lineage.
4. **Start finite trial** is a separate explicit action through existing Study
   continuation/admission. External execution first requires its existing exact
   material approval. Built-in execution remains owner-only.

Cloning, editing and preparation launch no Run, consume no execution grant and
charge no attempt. No automatic training, retry, resume or scientific promotion
is introduced. A branch copies a finite Study limit; it does not transfer a grant.

## Public operations and failure handling

New independently negotiated v1 operations are `studies.lineage`,
`studies.lineage_trial`, `studies.record_lineage`, `studies.branch_trial` and
`studies.prepare_branch`. `agent_api.py` owns closed schemas, current scope
requirements and contract hashes. Existing closed Trial and legacy registry
contracts are unchanged. Inspect requires current catalog inspection; writes
require current edit authority. Existing Study creation remains owner-only.

All three writes reconcile actor/operation/request-key/body receipts before
checking newer revisions or reading changed capture files. Changed bodies cannot
reuse a key. Graph/Study creation, lineage attachment, required audits and their
receipts commit atomically through existing owners. Concurrent identical branch
deliveries return the first committed result. A lost acknowledgement retains an
unknown outcome; the UI retains the exact request for explicit reconciliation.
It never automatically retries a mutation. Origin actor journals retain completed
writes after navigation; another actor cannot display them.

Overview reads use saved structural material identities and the latest five
bounded Run metadata summaries per Trial, without opening capture/artifact bytes
or probing runtimes. Full byte access and comparison remain in their existing
owners, including current input-disclosure checks. The baseline action opens the
existing comparison UI; exact checkpoint, evaluation artifact, metric definition
and comparison mode selectors still determine compatibility. No ad hoc delta is
computed from graph labels or cohort membership.

List pages contain at most20 Trials plus exact off-page parent/baseline references.
Later pages require the structural lineage revision, which changes when Trials or
sidecars are appended; live Run progress does not change this structural revision.
The UI holds at most100 Trials, supports exact cohort filtering, zoom and scrolling,
and labels partial windows. Layout order is not a chronology claim. Keyboard
controls and textual relationships provide the same selection/navigation path.

## Storage and verification

Schema10 is an explicit additive, quiesced migration; ordinary startup refuses
older catalogs. Follow [workspace storage](workspace-storage.md) for stopped-writer
backup, upgrade, verification and unknown-commit recovery. Older schema hashes and
restoration remain supported; missing lineage is never synthesized during upgrade.

`tests/test_experiment_lineage.py` exercises real PostgreSQL immutable identities,
retained branches, atomic audits/receipts, concurrent delivery, permission/revocation,
pagination, cold overview, explicit migration and restore. The controller regression
checks stale deliveries and actor-isolated reconciliation. The actual browser gate
in `tests/browser_model_development.cjs` authors a root Trial, runs CPU training,
branches into a second Study through Pipeline, edits and captures the clone, runs
it explicitly, compares exact checkpoints and captures desktop/mobile light/dark
screenshots. Its tiny authored CC0 fixture qualifies the workflow, not model quality.
