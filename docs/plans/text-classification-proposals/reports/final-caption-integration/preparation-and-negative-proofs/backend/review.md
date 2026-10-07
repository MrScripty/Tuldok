# Independent backend and admission-boundary review

Reviewed published PR18 head `12b174f7a7b2fd6aa36d71da450ad657a5443114` (tree `931c34e0d5123b6eb4d33456b428026c72be7105`). Read-only remote branch and PR18 head both match. Relevant runtime, static, tests, scripts and CI are byte-identical to reviewed runtime `c5500cba5021949bccf45d2124ee5e2910dc5c92`; working tree is clean. Source hashes and remote ref evidence are in `receipt.json`.

## Blocking finding: P1 fresh URL validation mismatch

`static/text-classification-proposals.js:37` validates gateway URL with a 4096 UTF16-unit bound and WHATWG `new URL(raw.trim())`; `text_classification_proposals.py:164` validates raw Unicode/codepoint length at 2048 and `ai_http.validate_url` uses Python trimming/whitespace/urlsplit rules. The frontend accepts seven distinct bounded cases the backend rejects before admission: ASCII URL2049 codepoints, lone surrogate, leading BOM, internal U+0085, missing authority slashes (`http:127.0.0.1:8000`), one slash (`http:/127.0.0.1:8000`), and backslash authority.

Persisting this client-valid/backend-invalid body before POST creates a durable unknown-admission trap if the definite400 acknowledgment is lost. Reload restores the same body; authoritative exactGET404 cannot resolve it; changing URL is blocked by frozen-intent ownership; exact retry returns400 but `static/text-classification-proposals.js:268` does not clear because `previous` exists. The interaction reviewer independently reproduced this complete sequence with real synthetic HTTP plus the actual form VM; see `../interactions/url-lost-refusal.log` and `../interactions/url-real-refusal.json`. This reviewer independently confirmed the grouped frontend/backend validation causes in `url_validation_comparison.json`; no transport or inference was required.

Ordinary URL, ASCII2048 and astral2048-codepoint URL controls pass both validators. The astral control has4074 UTF16 units, so reducing a JS `.length` limit to2048 would incorrectly reject an authoritatively valid input. Outer U+0085 is also a reverse mismatch (frontend refusal/backend acceptance), distinct from the availability trap. Request/source IDs ending in newline are rejected by both; no ID-regex issue found.

## Backend contract scope

Source review found no additional actionable defect in strict offered-label validation and explicit abstention, exact source/prompt/provider/labels/revisions freezing, bounded summary projection, request-ID intent conflict and authoritative recovery, restart/cancel fencing, or transactional idempotent draft Apply. Apply preserves acquisition provenance and does not grant human review. Previously retained c550 evidence contains18 independent boundary probes and the46-gate aggregate; these were not rerun in this narrow published-source/URL review. The newly reproduced admission trap supersedes any inference of full lifecycle clearance from those earlier results.

No repository source/evidence was modified. No real inference, downloads, credentials, public writes or integration were performed. Integration remains blocked pending a validation/recovery repair and exact final caption repair SHA; intermediate caption `4ed5466fd764e938999cca1d535e9a33379271a0` was not integrated.
