# Single-image caption proposals

Status: Verifying, local only. Parent selected this M2 image slice on 2026-10-07.
Base `ae094770cfebc68b73d91bc163a0043a4ab117dc`; isolated branch
`feature/caption-proposals-local-20261007`, worktree `/workspace/Tuldok-caption-proposals-local`.
Parent owns review/publication/integration. Main and PR16 remain frozen. Retain this
worktree/branch for parent review; no public writes or cleanup before disposition.

An explicitly selected existing image can receive one bounded Pumas-compatible
chat caption proposal. One request runs at a time. Served non-image model listing
does not prove vision or structured-output capability; request failure is visible,
without another model, automatic retry, or text-only fallback. Original image,
generation prompt, acquisition provenance, protected families and rights stay owned
by Dataset/Workbench. Schema checks never prove caption quality or grant approval.

CaptionProposals owns persisted attempts, exact bounded submitted JPEG and prompt,
request/response hashes, provider/model/configuration, captured source/target
revisions, cancellation/interruption and reject/apply receipts. Workbench owns
atomic target/history updates and target-associated proposal evidence. Applying
rechecks both revisions and current source hashes, saves exactly one draft caption,
and commits its linkage with the proposal receipt. Repeat application reconciles
lost responses without saving again. Later explicit human review preserves the
target evidence; a changed caption/task removes it from the current projection but
retains history and the original proposal. Export consumes the existing record
snapshot, including this target evidence, without changing imagefolder metadata.

Write set: `caption_proposals.py`, `workbench.py` (transaction and target evidence),
`app.py` (composition/routes), `static/caption-proposals.js`, `static/workbench.js`
(editor hooks/guards), `static/workbench.html`, `.gitignore`, `.github/workflows/tests.yml`,
`README.md`, new caption-proposal Python/controller/HTTP/browser fixtures and this
plan directory. `synthetic.py`, `image_generation.py`, dependencies and prior
reports are outside scope. Reuse existing cancellable HTTP; no provider registry,
new image store, batch queue, credentials, downloads or real inference.

Acceptance: controlled real HTTP receives actual oriented image bytes; bounded
complete JSON is required; exact evidence persists after reopen. Invalid catalog,
vision errors, response failures, cancellation during catalog/body, late output,
restart and fresh-request recovery cannot publish targets. Stale revisions,
missing/deleted/tampered images, concurrent/repeated application and injected
transaction failure preserve authoritative state. Controllers and real Chromium
exercise request/application double clicks, later edits, selection changes, lost
responses, reject, navigation/reload, draft-only application, stale fixed sets,
explicit review and actual downloaded ZIP consumption by the unchanged pinned
caption validator. Run all 40 inherited gates plus new supporting/browser gates;
retain fresh outputs separately and preserve historical report bytes. Independent
review examines the exact committed local candidate. Real-model valid output and
semantic quality are explicitly unqualified; final UI choices remain pending.

Focused qualification: 15 Python tests, controller ownership checks and the real
controlled-provider Chromium workflow passed. Aggregate exact-source qualification
and independent review remain pending.

Next slice: finish aggregate qualification and review, then return the tested
local commit to the parent for publication review.
