# PR111 captured CPU browser qualification

Base: `beead92d54e33e70eb9df82e872adf14ff314c91`. Repair owner:
`fix/retained-analysis-ci-qualification-20261020`; root owns serial integration.
The write set is the existing `tests/browser_model_development.cjs` gate and
this evidence directory. Production code and operation contracts are unchanged.

Both original captured CPU jobs reach actual training, branching, correction
and comparison, then time out at line 556. The obsolete assertion waits for
`Evidence access revoked` inside `.model-evidence`. The accepted Runs owner in
`static/workspace-real.js` removes that private panel and puts the denial in
`.real-status`. Its exact original output shows the denial, no Run rows and no
private result content. The next explicit Refresh action was never reached.
[Original failures](original-failures.json) retain all four run/job identities,
exact failure excerpts, checkout/source bindings, timestamps, full decoded-log
hashes and local raw MCP response/metadata paths.

The repaired assertion still injects the same 403. It waits for the Runs-owned
status and requires zero private model panels, metric grids, retained charts,
Run rows, checkpoint controls and probe controls. Only an explicit Refresh may
restore the exact third Run, its two checkpoints, metrics and rendered retained
SVG. The browser receipt records the observed denial and recovered result.

[Actual browser receipt](receipt.json) and [execution log](model-development.log):
passed, including all existing checks and the strengthened H5 denial/recovery.
[Qualification](qualification.json) binds the exact tested source hashes.
`node --check tests/browser_model_development.cjs` and the existing
[model controller suite](model-controller.log) passed.
This browser uses normal app/HTTP/PostgreSQL, authored image import and review,
frozen release creation, real CPU training, correction and exact comparison.
The denial itself is a controlled HTTP substitution; actual credential
revocation/export enforcement remains separately attributed to the existing
[authenticated integration acceptance](../m4-integrated/acceptance.md).
The supporting model controller suite uses controlled transport and is not
runtime training evidence.

Local qualification uses PostgreSQL 17.6, Python 3.12.14, Torch 2.8.0+cpu and
headless Chromium with the existing no-sandbox/software rendering flags and
an isolated browser profile. Only preregistered fresh schema
`catalog_8faa508de2e54448925420da15fa406c` is owned here. A local launcher creates
that catalog through normal `Metadata(dataset_id=...)` before executing the
normal app. All authored image data enters through the normal UI. Runtime source trees
remain unchanged. [Exact schema cleanup](schema-cleanup.json) confirms all three
observed Runs completed, the app stopped and only this schema was removed.
This local environment supports the affected browser claim;
GitHub's distro runtime provisioning and downstream package capture/fresh
consumer steps are separate CI claims and are not represented as rerun here.

The shared lifecycle failure is the canonical author fixture's equality check
against a now-evolved SDK. PR108 owns its separate frozen-source-authority test
repair; root propagates it through the predecessor integration. It is not part
of this repair. No model quality, scientific acceptance or CUDA claim is made.
No remote push, rerun, cancellation or merge is performed by this worker.

The task-created worktree `/workspace/Tuldok-retained-ci-repair-20261020` is
retained-protected by the named repair branch for root's review/integration.
Root owns its next disposition and safe cleanup after serial acceptance;
unrelated worktrees are outside this worker's ownership.
