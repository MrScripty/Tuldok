# Independent integrated interaction review: 8235672

Exact candidate: `8235672a8482e10e95df7a6d5b05540325f66816`, integrated from caption head `10de10b` via `71752fa` plus the classification URL repair. This is a focused review receipt, not approval for integrated qualification or publication. No source edits, commits, inference, downloads, credential changes, or public writes were performed by this reviewer.

## Confirmed blocker: two native pages can acquire different classification admissions

`native-two-pages-probe.cjs` runs the actual application/controllers in two Chromium pages sharing an origin. Both have previously read empty origin recovery storage. An external exclusive Web Lock holds the admission key while both native forms submit different author intents; then that lock is released. The fixture holds each POST before network transport.

Two unmodified runs on exact823 failed: both pages reached POST with different request IDs, and both later read recovery storage containing only the second body. Thus the admission Web Lock plus a localStorage reread/write does not reliably enforce the intended single durable identity across native pages. No backend/provider call is needed to reproduce the identity overwrite; both requests remained held before transport. If those requests subsequently proceed or lose acknowledgements, the original body's durable recovery evidence is already overwritten.

Evidence:
- `native-two-pages-823.log`: first page ID `cd95874f3bc7457dbfefee1c2794d861`, second page ID `4fbddcd02f444958bd60d915678d009e`.
- `native-two-pages-823-rerun.log`: independent second failure, first page ID `7f414a0cc8ed43be9b316aacc7406083`, second page ID `770186d989f049158eadc6d0a64e7dee`; node exit1 retained.

Both failures timed out waiting for a total of exactly one captured POST because two were already captured. Diagnostics include both exact bodies, shared stored second body, busy/paused state and empty browser exception list. Classification JS SHA-256 stayed `0f134d74470754f7c5b90832cb452606f7ddbee0156d630a1212a664223b53fd` throughout.

A variant wrapping lock callbacks and a storage-tracing-only variant passed (`native-two-pages-instrumented-823-01.log`, `native-two-pages-storage-trace-823-01.log`), demonstrating timing sensitivity. They do not supersede the two concrete failures. Cross-renderer localStorage visibility at Web Lock handoff is a plausible cause; this is an inference, not a proved browser implementation diagnosis. The single-identity admission guarantee needs a reliable shared transactional authority and independent native requalification. No runtime repair was attempted here.

## Confirmed blocker: caption whitespace guidance creates impossible durable recovery

The final-caption10de controller remains byte-identical in candidate823. `captionProposalRecoveryBody` accepts guidance containing three ASCII spaces and persists it, while real backend admission returns HTTP400 before any job or worker starts. If that first acknowledgement is lost, a full controller reload restores the invalid guidance, exact-ID GET404 retains uncertainty, correction to valid guidance sends zero POSTs, and an explicit exact repeat receives HTTP400 while retaining the same pending identity.

`caption-whitespace-refusal-probe-823.cjs` uses the actual form handler and shared tab storage; `caption-refusal-http.py` provides real loopback POST/GET/POST. `caption-whitespace-refusal-823.log`, `caption-whitespace-823-real-refusal.json`, and `caption-whitespace-823-captured-body.json` retain exact823 evidence: HTTP400/404/400, zero jobs, no worker, zero provider transport. Correct the frontend/backend admission boundary before caption approval. An earlier preliminary attempt failed only on a cross-VM prototype comparison; `caption-whitespace-first-attempt.log` is preserved and successor assertions normalize the captured body.

## Focused classification URL repair passed

`classification-url-repair-probe.cjs` independently passed 13 invalid URL cases on exact823, including the reported 2072-codepoint ASCII URL, repaired authority spellings, empty userinfo, port0, query/fragment, unpaired surrogate, internal Python whitespace, and unsupported scheme. Each produced zero POST/storage/pending state and no storage error latch. Correction on the same document produced exactly one explicit POST with the raw accepted URL preserved, followed by authoritative receipt clearing.

The validator accepted a URL of exactly 2048 Unicode code points containing astral path characters. Existing invalid persisted evidence remained blocked and retained after exact-ID404; the repair does not silently discard older unresolved evidence. `classification-url-repair-823.log` retains results. The original negative published12b URL-defect evidence remains unchanged outside the repository at `/workspace/scratch/tuldok-classification-integration-prep/interactions/`.

## Other positive integration checks

`composed-cross-feature-probe.cjs` passes 16 scenarios on exact823 using the actual workbench, instruction-response, caption-proposal and classification-proposal controllers. Five additional cross-feature cases establish text/image form and panel separation; coexistence and independent reconciliation of caption tab storage and classification origin storage; late caption Apply acknowledgement preserving a later text answer; late classification Apply preserving later image edits; and caption Reject not acquiring ownership during an independent annotation save. The 11 prior classification composition scenarios still pass. See `composed-823.log`.

`native-cross-feature-probe.cjs` passed on exact823 with the actual application, two Chromium tabs and separate bounded synthetic caption/classification providers. It proves full document reload restores both distinct pending identities without inference, a new tab sees the origin classification identity but has no caption tab identity, changed second-tab classification intent sends no provider request, explicit identical repeats preserve original IDs, caption and classification recovery stores reconcile separately, and a held successful caption Apply acknowledgement preserves a later unsaved text answer. Exactly one synthetic model request reached each provider; image Apply granted draft only and the text annotation remained unchanged. See `native-cross-feature-823.log` and `native-cross-feature-session.json`. This positive restored-pending scenario does not cover the failing empty-storage two-page race above.

HTML parsing found 202 unique IDs, zero duplicates, both independent forms and the expected script order. Caption JS matches10de; workbench JS differs from10de only by the two classification hooks (record shown and save busy guard). See `html-composition-823.json`.

## Remaining work

The classification URL parity fix passes this focused review. Integrated signoff remains blocked by caption invalid-guidance recovery and native two-page identity overwrite. Parent coordinates the updated caption head and any admission-authority repair. No full integrated aggregate qualification or publication was run here. Real-provider compatibility and semantic quality remain outside bounded synthetic review scope. All prior published and preliminary negative evidence was preserved; this exact823 receipt will remain separate from future successor receipts.
