# Exact caption input validation qualification

All 43 registered gates passed on source `9483d4a2f5c1391b3f882e107cee6846aeb36a39`,
tree `0fe33807c03e582c3a5ce9f4403be37e570e8f59`, based on published PR17
`10de10b6710976570ace33b033ffb2349995edec`. Python: 257 tests in 86.181s,
including 22 caption owner/API tests. All controllers, syntax checks and 21 real
Chromium invocations passed. All 1,305 inherited report files remain byte-identical;
20 other existing local heads remain unchanged. Workflow registration, backend
production code, HTML, PR18, `synthetic.py` and `image_generation.py` are unchanged.

Whitespace-only guidance was a reachable fresh-input defect: HTML required accepts
it, the old controller persisted it, and the backend refused before admission.
Losing that error response left an unresolved exact intent that could not be
corrected. Negative controller and real Chromium logs reproduce the published
source with a lost-400 hook and whitespace guidance retained in recovery storage.
The repair validates every exact field before persistence, without changing the
admission/recovery ownership contract or normalizing the persisted body.

Guidance must be nonblank under Python Unicode whitespace rules, at most 2,000
code points, with no unpaired surrogates. Models must be nonblank, at most 200
code points, with no C0 controls or unpaired surrogates. URL validation checks the
original authority before WHATWG parsing can repair it, all userinfo including
empty userinfo, scheme, hostname, nonzero valid port, internal whitespace/control
characters, surrogates and query/fragment semantics. The 2,048-code-point URL bound
applies after the backend's stripping and trailing-slash `/v1` normalization,
before WHATWG percent encoding. Accepted values stay exact for intent hashing.
Frontend parsing still conservatively excludes some permissive Python URL shapes;
the independent review documents those bounded differences. URL/model parser
mismatches are validated contract cases, without claiming ordinary-form reachability
for every shape or a security vulnerability.

Independent interaction review found one further P2 on checkpoint `e89cf763`:
a served URL with 33,000 trailing slashes fits the normalized backend URL bound but
exceeds the exact recovery JSON envelope, latching a false storage failure. The
successor validates that envelope before storage. Exact 32,768 UTF-16-unit JSON
is accepted unchanged; 32,769 is a correctable fresh error. Tests cover trailing
slashes, discarded `/v1`, and leading/trailing Python whitespace padding. Genuine
storage failures and previously invalid stored evidence stay retained and fenced.
The checkpoint's full successful aggregate run and the review finding are preserved.

The registered controller checks an 86-case shared table against the actual Python
validators, fresh correction, normalized versus raw Unicode bounds, IDs/revisions/
seed and exact storage limits. Python tests prove invalid static inputs create no
attempt/model request or record changes; accepted normalization preserves the raw
intent hash and an unchanged replay invokes inference once. Independent composition
review exercised 14,058 static cases and 36 envelope cases, including nine exact-cap
acceptances and 18 over-cap refusals. Independent interaction review exercised 1,209
URL cases and lost-reply/reload/404/repeated-refusal identity fences. Both reviews
report no remaining P1/P2 on the final source. Large generated review case tables
are retained as deterministic gzip files; `compressed-artifacts.json` gives their
decoded sizes and hashes, and their generators and source receipts are included.

Real Chromium prevents ordinary whitespace guidance and injected surrogate input
before POST/storage with a lost-400 hook armed. It lists a served model using the
actual long-slash URL, refuses the oversized exact envelope and corrects to a
working URL and 2,000 emoji without reload. A separate transport fault deliberately
changes an initially valid request to whitespace after local validation, obtains
a real backend 400 and loses the reply. Exact lookup 404, a fresh-document reload
and changed input cannot clear its original identity; only an explicit unchanged
repeat proceeds. This fault case does not claim invalid fresh input passed the
repaired validator. Existing cancellation, history ownership, held GET/admission,
model-once replay, quota failure, draft-only application, Reject/editor ownership,
stale fixed selections, separate human review, downloaded ZIP/pinned consumer,
keyboard and desktop/390px layout gates remain passing. No runtime exceptions.

Scope is the caption frontend validator, supporting tests and evidence. No API
contract changed; classification should independently apply equivalent whitespace,
exact raw model/guidance bounds, original URL checks and recovery-envelope preflight,
while retaining its own recovery namespace, owner and review rules. No PR18 edits,
merge, manual CodeRabbit request, credentials, network-setting changes or downloads.
All providers and records are controlled local fixtures. Real model quality and
backend compute-stop remain unqualified; recovery remains scoped to the same tab
and origin. The final publication identity and hosted CI receipt are in the parent
handoff; this report identifies the exact executable source qualified locally.
