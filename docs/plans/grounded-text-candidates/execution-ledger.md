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

## 2026-10-02 — independent review transport repairs

Hosted CI passed the initial checkpoint `d849da21ffb1db192e585428f5b60c1eea1d7a91`, including the controlled-provider Chrome workflow. Independent review then exposed three gaps that green fixtures had missed: valid JSON delivered before declared HTTP body completion; lossy UTF-8 replacement decoding of a valid UTF-16 response; and cancellation not reaching stalled model discovery.

This repair rejects a response with outstanding Content-Length before candidate decoding, stores the exact bounded received bytes as `raw_response_base64` (the SHA-256 hashes those decoded bytes), and retains `raw_response` only as a strict, lossless UTF-8 view. Both raw representations are omitted from polling and retained on exact job retrieval. Existing persisted jobs remain readable; prior lossy bytes cannot be reconstructed. Model discovery now receives the same cancellation event and socket ownership as chat, retaining the existing 15-second discovery deadline.

Three actual-worker HTTP regressions exercise a complete candidate JSON body declared ten bytes too long, valid UTF-16 and UTF-8 response hashes across reopening, and cancellation while the model catalog stalls before headers. The catalog test also verifies that a fresh job can complete afterward. Narrow independent rereview and exact repair-head CI remain pending. Real model quality remains unqualified.

Repair local evidence: all 66 Python tests pass, including all 53 M1 regressions; controller deferred-response tests, JavaScript syntax and whitespace checks pass.
