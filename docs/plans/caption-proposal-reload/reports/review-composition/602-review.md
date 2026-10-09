# Reload recovery successor composition review

Exact reviewed head `602d25f5d4dd7a904a6d1aaae23824838d0790aa`, tree
`0563406e0db0d12ae60e284cba2bb054edffb560`, against base
`07ec464ba050cd532a2508ce86570a1ce9bcd394` and narrow repair delta from
`e73c688a1334652da0552baaafb4b308090a78ba`. No findings remain in this bounded
reload/storage-owner review. Original e73 review, negative probe and receipt
are retained unchanged.

The accepted history ownership P2 is repaired. Live entry is read before submit
and before/after asynchronous lookup; pageshow adopts it synchronously and
restores exact form settings. Store/remove compares live entry with owned memory
before changing it, failing closed when ownership differs. Same-request equality
keeps existing object identity for unchanged entries, preserving in-flight fences;
changed entries replace stale pending memory. A stale original first-refusal may
not remove another document's newer request, and a late success looks up the live
request rather than dispositioning it from the old acknowledgement. GET404 and
failed-repeat ambiguity remain retained; definite fresh refusal and authoritative
reconciliation retain their prior proof scopes. Storage errors still fail closed
and no automatic inference replay is added. Backend/body/hash contract unchanged.

Executed complete reload controller including history-clear/history-repeat,
late-refusal/late-success, held-get, pageshow read failure and prior storage-error
cases; passed. Combined caption controller also passed. Exact final reload test
on predecessor e73 fails at pageshow synchronous adoption. Independent repaired
history probe separately confirms adoption of newerID2, staleID1 repeat refusal,
known older GET plus newer exact404 cannot clear ID2, and another full document
continues to refuse changed intent. JavaScript syntax and git diff --check pass;
source/tree remain exact and worktree clean.

No production/tracked report edits, aggregate/browser execution, remote/bot calls,
merges, downloads, real inference or unrelated feature work. Observations use
controlled two-document VM schedules rather than an actual browser BFCache run;
parent owns aggregate/browser qualification. Closing tab, explicitly clearing
storage and cross-tab/device recovery are outside the declared guarantee.
No real-model quality or performance claim.
