# Execution ledger

## 2026-10-02 — discovery and admission

Verified M1 published green head and branched from its remote commit. Reused the actual Pumas gateway model/chat contract rather than inventing a text generation endpoint. Selected class-preserving source rewrites as the smallest consumer-compatible grounded production slice: output fits the already implemented text-classification release contract. Model-produced quotes must match captured canonical source spans, with semantics left for human review. No real inference attempted.


## 2026-10-02 — bounded implementation and local evidence

Implemented proposal persistence and one owned worker, using the existing Pumas-compatible `/v1/models` and `/v1/chat/completions` transport. Consolidated non-image model decoding behind the existing `/api/generation/prompt-models` application route; the model list does not fabricate structured-output capabilities. Added optional cancellation to the shared HTTP transport, with no automatic inference retry. Interrupted requests remain inspectable after restart.

Candidates retain a captured canonical source, revisions/class, requested model/seed/instruction, exact system prompt/version/hash, canonical request hash, bounded raw response/hash and reported model where supplied. Complete candidate decoding enforces class identity and exact Unicode source quotes, explicitly without claiming semantic verification. Admission rechecks source revisions and atomically inserts a draft Workbench record plus its proposal link. Repeated successful admission returns the same record; rejection is terminal and review races conflict. Rights and protected ancestry propagate into existing frozen releases.

The provisional UI shows captured sources, proposed text/class/evidence, review notes, rejection and draft admission. Model lookup responses are fenced to their URL; proposal polling stops on terminal outcomes/page exit and preserves notes/open panels. Existing editor navigation fencing is retained. No model proposal becomes release-eligible merely by passing structural checks or being admitted.

Local evidence: `python3 -m unittest discover -s tests` passes 63 tests (53 M1 + 10 grounded tests); actual-controller deferred-response tests and JS syntax pass. Tests include actual controlled HTTP model/chat requests, source mutation while inference is pending, cancellation, byte limits, truncation, invalid evidence/classes, atomic rollback injection, idempotent admission, reopening, and real release archive consumption after human review. A dedicated hosted Chromium fixture covers proposal review/admission/release/rejection/cancellation/reopen; it has not yet run. No real Pumas inference or model-quality acceptance is asserted. Independent review and publication remain pending; main and green M1 head are unchanged.

## 2026-10-02 — publish coherent checkpoint for review

The milestone-publication instruction now permits preserving this coherent M2a checkpoint on its dependent branch before final review. The verified implementation tree `29df084ab81b14315819eb429f728d1118d198fe` has 63 passing local Python tests plus controller and syntax checks. Independent review, exact-head hosted browser/CI evidence and real-model qualification are still pending. Publish only `feature/grounded-text-candidates` with a draft PR targeting `develop/dataset-workflows`; neither main nor the green M1 branch is changed. Presentation proposals remain excluded.
