# P3a authority admission

P2 exacthead2476a7daa339597557d29eb6e691327895d8c48c passed hosted UI14/14 and lifecycle125/125 steps. PR46 remains a draft, unmerged. Refreshed main remainsc522bf6. P3a branch isolates current-client authorization; P3b external execution follows.

P3a candidate: explicit local actors across current operations. P3b external custody follows on separate feature branch; P3 overall gate remains pending until both qualify. No implementation until P2 exact-head CI passes. This split contains the large existing-client migration and keeps runnable checkpoints.

Canonical Access owner shares catalog PostgreSQL metadata, explicit schema7 with retained TABLES_V6; narrow actors,credentials,audit tables (approval storage deferred to P3b where first consumed). Random opaque >=256bit tokens stored only SHA256. Revocable credential scopes; actor kind owner/human or agent resolved solely from server state. No body actor/role; no localhost owner identity; no production testmode; no omitted-actor fallback.

Explicit local CLI bootstrap using Metadata+Access (not full Dataset) creates initial owner and one-time bootstrap credential written to new mode0600 private file, no token logging or URLs. Refuse rebootstrap once owner exists. Browser session exchange consumes one-time secret and issues expiring opaque HttpOnly SameSiteStrict Path=/ cookie. Local HTTP no Secure flag; session grants authenticated owner. CLI can issue a fresh one-time login token under local admin filesystem authority; tokens never in project files/URLs/Library. Owner-authenticated credential issue/revoke operations issue agent scopes as allowed subset, never approve-review/approve-execution/admin. TTL bounded, live revocation checked on every admission. Raw token shown only once in explicit credential issue response; don't log it.

Scopes: inspect; edit/propose; execute; cancel; freeze; approve-review; approve-execution; expose-holdout; admin. Owner has all. Agent can receive inspect/edit/execute/cancel/freeze/expose-holdout only where explicitly issued; humanreview denied regardless request booleans. P3a current inference operations require execute; any material privileged approval semantics must be decided explicitly rather than bypassed because legacy.

ContextVar holds server-resolved immutable actor context, verifies catalog identity+credential current grants, reset at request end. Direct domain operations require explicit bound session. Multiple catalogs use explicit nested scopes (or reviewed catalog-keyed context if simpler and tests need it); no Dataset auto-binding. Every externally callable domain method requires named scope before IO/mutation; private internal methods are not public API. Composition among owners retains same context. Every HTTP API/read/download authenticates before route dispatch/body ingestion; static/login minimal closed exceptions. Owner/agent bearer supported; cookies same-origin POST mandatory by normalized Origin or strict same-origin Fetch Metadata with no cross-site fallback. Review exact browser behavior and script migration. Project configured-root/loopback defenses retained.

Human approval: owner request to save human_reviewed is a fresh explicit approval bound transactionally to exact before record/source revisions plus proposed task/annotation/groups/review content. Audited target digest/revisions and actor persist separately; don't pretend historical review had authenticated actors. Preference/response reviews same boundary. Agent proposals remain drafts. Trusted procedural verification stays separate and cannot mint humanreview. No actor fields added to existing frozen row schemas merely to project attribution; audit lookup supplies current attribution, legacy missing labels explicitly.

Execute approval P3b must bind project, graph/recipe/source/runtime/input identities, params/resources/permissions. Agent can consume owner-approved exact request once; idempotent reconciliation same actor returns existingadmission. P3a must either implement same approval owner for existing execute paths or keep those paths owner-only until P3b, with explicit client migration and no scope-only agent provider execution shortcut. Existing trusted internal generation continuations need durable admittedactor/request capability, not ambientowner. Public start authorizes before scheduling, continuation bound to the admitted exact job and effect; revocation blocks new admission, alreadyadmitted bounded work canfinish. Child thread gets explicit continuation context; cannot call unrelated edit/review/admin operations. Details require full owners inventory.

Audit: actor, credential identifier (never secret/hash), action, target revisions/digest, approval, outcome; append-only. Success audit and mutation same transaction. Failed auth/permission audit durable without accidental partial mutation. Bound text/target sizes. Static/cold immutable file readers need no catalog actor.

Tests: explicit fixture bootstrap and actor-binding helper; real HTTP bearer/cookie login and CDP session fixture with credentials limited exact application origins. No auth monkeypatch/injected handleractor. Migrate all current directdomain/HTTP/browser callers, fixturethreads and backgroundjobs. Denials: missingcontext, wrongcatalog, expired/revoked, scope escalation, forged humanreview, staleapproval, cross-origin, reusedbootstrap, unauthenticated legacyAPI. Existing realRun and old+new backuprestore gates. Independent review and exactheadCI before P3b.

Decision for review: P3a existing inference/generation/training starts remain authenticated owner-only. Agents can inspect/propose/edit/freeze/cancel only as issued; even an execute-scoped agent receives an explicit unsupported/permission denial until P3b material approval consumption qualifies. Owner action itself binds its exact current request; P3b introduces durable transferable approval records for agent/external execution. This keeps existing owner workflows runnable without claiming agent execution complete. Store review actor attribution in audit joined by record/revision, not extra frozen-row keys; label missing historical attribution as legacy. Tests demonstrate all public execution starts deny agent role, including old legacy AI routes.

Independent review resolutions: add one closed access_admissions table for existing asynchronous jobs (not future execution approvals): catalog, actor+credential IDs, job kind/ID, immutable request digest and finite allowed effects. Existing start/retry/resume binds this receipt transactionally before scheduling; jobs receive a one-job internal continuation context, never copied owner scopes. Only owner admissions can create these receipts. Domain guards match explicit action+job target against the retained receipt. Revocation denies new admission but bounded already-admitted work may finish. Narrow internal system reconciliation/shutdown context can only inspect/reconcile/interrupt/drain retained work; cannot start, replay, create ordinary data or grant review. Legacy interrupted jobs retain legacy attribution; resuming requires a fresh owner admission. These internal contexts are not transport endpoints or public agent operations. Cancellation scope explicitly permits cancellation of any job in that catalog; no implied cross-catalog authority. Bootstrap consume+session creation atomic and login exchange same-origin. Unauthenticated-denial audit actor null; authenticated denial records actual actor, never asserted request fields; denied mutations roll back before durable denial audit.

Binding implementation refinement from independent review: @authorized(scope,action) is a small explicit guard/context only; it MUST NOT open an outer transaction. synthetic.start/grounded.start reject existing transactions, and Runs commits admission before dispatch. Preserve each owner's transaction/lifecycle boundary. Insert success audit/admission inside its existing mutation transaction, with exact record revisions/review digest; short helpers may be explicit opt-in, never implicit wrapping of spawn/network/filesystem lifetimes. Denial audit follows rollback, operational failure and CommitOutcomeUnknown remain distinct. Auth requires no catalog audit write for successful ordinary inspect; privileged actions and denials retain evidence. Pure module-level frozen validation functions remain unauthenticated/cold; stdlib-only access.py import added to each pinned worker closure if decorators require it.

Inventory: three HTML entrypoints,27fetch calls across16JSfiles,four APIhelpers;48runnablebrowser suites; approximately60Python test/helper files with136Dataset construction sites and29handler-owningfiles. Both legacy and newer API surfaces require explicit authentication. Internal provider fixture endpoints also require access checks; no testmode.

## Consolidated assigned write inventory

The assignments were recorded before each owner edited its files; this consolidated integration inventory records the resulting exact paths. The initial broad migration estimate was not an exact path inventory. Root additionally authorized the three qualification scripts after the caller audit identified them, and the auth HTTP tests and CI gate. No unrelated changes are admitted.

```text
.github/workflows/tests.yml
README.md
access.py
app.py
audio_assets.py
bulk_import.py
caption_import.py
caption_proposals.py
dataset_recipes.py
dataset_releases.py
docs/contracts/actors.md
docs/contracts/workspace-storage.md
docs/plans/generic-scientific-projects/execution-ledger.md
docs/plans/generic-scientific-projects/plan.md
docs/plans/generic-scientific-projects/reports/p3a-admission.md
docs/plans/generic-scientific-projects/reports/p3a-verification.md
docs/plans/generic-scientific-projects/reports/p3a/access-receipt.json
docs/plans/generic-scientific-projects/reports/p3a/domain-guard-inventory.json
docs/plans/generic-scientific-projects/reports/p3a/session-1280.jpg
docs/plans/generic-scientific-projects/reports/p3a/session-390.jpg
docs/plans/generic-scientific-projects/reports/p3a/source-files.json
grounded_candidates.py
image_generation.py
immutable_assets.py
meshes.py
metadata.py
native_detection_import.py
native_text_import.py
pipeline.py
preferences.py
projects.py
rheon_sequences.py
runs.py
saved_searches.py
saved_selections.py
scientific_fields.py
scripts/prepare_caption_fixtures.py
scripts/qualify_grounded_local.py
scripts/qualify_pumas_typed_actual.py
sequence_assets.py
sequence_batch_import.py
spatial_assets.py
static/app.js
static/audio-editor.js
static/auth.css
static/auth.js
static/bulk_import.js
static/caption_import.js
static/index.html
static/meshes.js
static/native_detection_import.js
static/native_text_import.js
static/pointclouds.js
static/pumas-typed.js
static/scientific-fields.js
static/sequence-batch.js
static/volume-editor.js
static/workbench.html
static/workbench.js
static/workspace-projects.js
static/workspace-real.js
static/workspaces.html
static/workspaces.js
synthetic.py
tests/auth_helpers.cjs
tests/auth_helpers.py
tests/browser.cjs
tests/browser_access.cjs
tests/browser_bulk_import.cjs
tests/browser_caption_dataset_integration.cjs
tests/browser_caption_import.cjs
tests/browser_caption_proposals.cjs
tests/browser_captions.cjs
tests/browser_classification_preferences_integration.cjs
tests/browser_combined_workbench.cjs
tests/browser_curation.cjs
tests/browser_curation_server.py
tests/browser_dataset_integration.cjs
tests/browser_grounded.cjs
tests/browser_image_classification_export.cjs
tests/browser_image_classification_server.py
tests/browser_images.cjs
tests/browser_images_real.cjs
tests/browser_instruction_responses.cjs
tests/browser_meshes.cjs
tests/browser_metadata_filters.cjs
tests/browser_metadata_server.py
tests/browser_native_detection_import.cjs
tests/browser_native_text_import.cjs
tests/browser_preferences.cjs
tests/browser_pumas_gateways.cjs
tests/browser_pumas_typed.cjs
tests/browser_pumas_typed_server.py
tests/browser_release_preview.cjs
tests/browser_rights_note.cjs
tests/browser_saved_searches.cjs
tests/browser_saved_selection_intent.cjs
tests/browser_saved_selections.cjs
tests/browser_scientific_fields.cjs
tests/browser_sequence_batch.cjs
tests/browser_sequences.cjs
tests/browser_sequences_actual.cjs
tests/browser_text_classification_proposals.cjs
tests/browser_text_classification_proposals_server.py
tests/browser_text_corpus_export.cjs
tests/browser_vlm_real.cjs
tests/browser_workbench.cjs
tests/browser_workspace_audio.cjs
tests/browser_workspace_audio_run.cjs
tests/browser_workspace_breadth.cjs
tests/browser_workspace_export_run.cjs
tests/browser_workspace_image_run.cjs
tests/browser_workspace_mesh.cjs
tests/browser_workspace_mesh_run.cjs
tests/browser_workspace_project.cjs
tests/browser_workspace_sequence_run.cjs
tests/browser_workspace_spatial.cjs
tests/browser_workspace_text.cjs
tests/browser_workspaces.cjs
tests/check_image_classification_consumer.py
tests/check_text_corpus_consumer.py
tests/qualify_spatial_retained_runs.py
tests/test_access.py
tests/test_access_http.py
tests/test_ai.py
tests/test_audio_data.py
tests/test_audio_training.py
tests/test_auth_controller.cjs
tests/test_auth_helpers.cjs
tests/test_bulk_import.py
tests/test_caption_exports.py
tests/test_caption_import.py
tests/test_caption_proposals.py
tests/test_combined_workbench.py
tests/test_curation.py
tests/test_dataset.py
tests/test_export_runs.py
tests/test_generation_job_api.py
tests/test_grounded_candidates.py
tests/test_image_classification_export.py
tests/test_image_generation.py
tests/test_image_training.py
tests/test_instruction_responses.py
tests/test_mesh_release.py
tests/test_mesh_runs.py
tests/test_meshes.py
tests/test_metadata_filters.py
tests/test_metadata_migration.py
tests/test_metadata_transactions.py
tests/test_metadata_workers.py
tests/test_native_detection_import.py
tests/test_native_detection_stack.py
tests/test_native_text_import.py
tests/test_pipeline.py
tests/test_preferences.py
tests/test_projects.py
tests/test_pumas_typed.py
tests/test_pumas_vision.py
tests/test_real_import_foundation.py
tests/test_release_preview.py
tests/test_rights_note.py
tests/test_runs.py
tests/test_saved_generation.py
tests/test_saved_searches.py
tests/test_saved_selections.py
tests/test_scientific_fields.py
tests/test_scientific_release.py
tests/test_sequence_batch.py
tests/test_sequence_release.py
tests/test_sequence_runs.py
tests/test_sequence_v2_runs.py
tests/test_sequences.py
tests/test_sequences_v2.py
tests/test_spatial_release.py
tests/test_spatial_storage.py
tests/test_synthetic.py
tests/test_text_classification_proposals.py
tests/test_text_corpus_export.py
tests/test_text_training.py
tests/test_workbench.py
tests/test_workspace_metadata.py
text_classification_proposals.py
upgrade_metadata.py
workbench.py
```
