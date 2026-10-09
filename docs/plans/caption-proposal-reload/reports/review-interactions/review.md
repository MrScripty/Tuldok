# Caption reload recovery interaction review

Exact source `e73c688a1334652da0552baaafb4b308090a78ba`, tree `6e5430329f47ac05b966516916e2ee422074fa95`, base `07ec464ba050cd532a2508ce86570a1ce9bcd394`.

## P2: stale document loses newer tab recovery

Store at `static/caption-proposals.js:24-33` blindly writes/removes the tab entry; pageshow at `:178` resumes polling without rereading it. Independently reproduced: cached A retains ID1, B reconciles it and stores unknown ID2, A pageshow plus GET ID1 removes ID2, then a new document POSTs changed ID3. With the GET held, A explicitly repeats stale ID1 and overwrites ID2 before POST. A late first-attempt 409 at `:172` also removes ID2. These are three manifestations of missing live storage ownership.

Reload/validate storage synchronously on pageshow, fence old polls, and compare expected live ownership before every write/removal, including refusal cleanup. Old completions must preserve newer unresolved IDs. The exact-source probes and suggested successor tests are retained in receipt.json.

The registered controller plus nested reload test passed. Independent positive probes passed held reconciliation/same-body repeat, refused-repeat retention, pagehide/poll fences and silent write/removal/readback failure checks. Base fails the held-reload changed-intent assertion as expected. Passing single-document checks do not cover the reproduced multi-document gap; acceptance is incomplete on e73.

Owner began successor edits while review evidence was packaged. Final bounded executions used explicit immutable e73 Git-object extracts, preserving exact test identity and avoiding evolving candidate source. No candidate writes, browser/aggregate runs, inference, remote actions or publication occurred. Controlled VM probes model document/storage ownership; parent owns real Chromium qualification and repair implementation.
