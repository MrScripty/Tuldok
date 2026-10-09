# Grounded text candidates (M2a)

Status: Active, coherent checkpoint publication for independent review. Dependent branch `feature/grounded-text-candidates` starts from green M1 remote `4047c2e1d90adeffc07daf24ccf30dfeb309d28e`; proposed PR targets `develop/dataset-workflows`. Main and the M1 branch remain unchanged. No inference credentials, paid calls, model downloads or presentation changes.

## Admitted bounded outcome

Given a human-reviewed text-classification source, ask a served Pumas chat model for 1–10 constrained rewrites. Retain exact canonical source/revision/hash, instruction, provider/model, request seed, complete bounded output identity, exact source evidence and validation results. Model targets are proposals: the label must match the selected source class, and evidence spans must quote that source exactly, but neither check proves semantic preservation. A person can inspect/reject a candidate or atomically admit it as a draft workbench record, then independently review its annotation before release. Parents and inherited protected groups preserve split relationships.

This is M2a, not all M2. Unconditional text synthesis, source-grounded Q&A/instruction tuning, multiple source contexts, entity rewriting and model-assisted image target suggestions remain outside this slice. Existing image generation remains Dataset/synthetic-owned. No model quality or real Pumas runtime qualification is claimed from fixtures.

## Boundary research and choice

Inspected Tuldok `synthetic.prompt_batch`, `ai_http.request/models`, `image_generation.models`, and Pumas Library source snapshot `445af474762bebac6cc3b690c29c010a187c72ef`, `rust/crates/pumas-rpc/src/handlers/openai_gateway.rs`. Pumas exposes `/v1/models` and `/v1/chat/completions`; image entries advertise `capabilities:["image_generation"]`, while text entries have no equivalent structured-output claim. Reuse the existing `/api/generation/prompt-models` application route and chat transport. Its shared non-image catalog decoder now serves both image prompt preparation and grounded text proposals; no parallel model-discovery route is added. Reject listed image-only models; treat a successful complete structured response as request-level compatibility evidence, not advance proof that a model supports all tasks.

Research basis: supplied Dataset Production's synthetic-strategies-and-verification and modality-production chapters separate generator, evidence check and human review; rewrites can change facts/labels; exact source quotes do not establish semantic grounding. Cooking the Cat's deterministic-control and bounded-development guidance informs revision checks and reversible draft admission.

## Owners and invariants

- Workbench remains text/annotation authority. Extract its existing text insert operation for atomic candidate admission; do not create a second asset store.
- `grounded_candidates.py` owns bounded proposal jobs, source snapshots, proposal states, rejection/admission, and one active worker. It does not replace the existing image batch job or HTTP transport. Jobs persist before launching, failures/cancellation remain inspectable, and interrupted jobs never auto-resume inference.
- Existing `ai_http.request` gains optional cancellation with explicit transport ownership. No automatic provider retry: a failed/cancelled/unknown result is recorded and user retry creates a fresh job.
- The source must remain at its captured target and source revisions on admission. A changed source cannot silently redefine prior evidence. Source grouping/parent edges survive through M1's lineage graph.
- Complete response decoding rejects unknown fields, truncated responses, wrong count/classes, invalid Unicode, duplicate outputs, malformed/out-of-range/incorrect quotes. These checks confer only `schema_and_exact_source_quotes`; all admitted records start `draft`.
- Admission and proposal-to-record link commit together; repeated acceptance returns the same record. Rejection is terminal. Concurrent review is revision-checked.
- UI binds requests to current source identity/epoch, displays captured evidence and limitations, and supports cancel/reopen/retry without silently starting new inference.

## Write set and acceptance

Write set: `grounded_candidates.py`, `ai_http.py`, `workbench.py`, `app.py`, `static/workbench.html/js/css`, `tests/test_grounded_candidates.py`, `tests/fake_grounded.py`, `tests/browser_grounded_server.py`, `tests/browser_grounded.cjs`, `tests/test_workbench_controller.cjs` as required, `.github/workflows/tests.yml` for dependent-branch coverage, this plan/ledger and the canonical M1/M2 plan milestone pointers.

1. Controlled served catalog and chat HTTP flow use actual existing paths, reject unavailable/image models, and decode proposals: passed local contract/HTTP tests.
2. Exact evidence and provenance, draft-only atomic/idempotent admission, human-reviewed release and preserved lineage: passed local persistence/archive tests.
3. Stale source, malformed/truncated/oversized response, cancellation, rejection and reopen/interruption are safe: passed local controlled-provider tests.
4. Initial checkpoint: 63 Python tests plus controller checks and permitted hosted Chrome flow passed. Transport review adds three actual-worker HTTP regressions; repair-head checks and CI are recorded in the ledger. Local browser restriction remains untouched.
5. Dependent draft PR #2 is published. Independent review found three transport/provenance gaps; repairs require narrow rereview and fresh exact-head CI.
6. Real Pumas/model qualification: unavailable until an approved runtime and inference authority exist; do not infer from fixtures.

Exactly one next slice: publish and independently rereview the bounded transport repairs, inspect their exact-head CI, then qualify the remaining M2a gates.
