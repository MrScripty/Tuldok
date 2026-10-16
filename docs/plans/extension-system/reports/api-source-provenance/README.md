# Exact source provenance after Git publishing credential expiry

The original ordinary-agent CPU qualification used local source commit
`e1bc02a68355876ec64e5e1e272019c2018b5c63`, tree
`a6bef5761c75f89af8d7cc2e3f8c01a828f4f284`. Git CLI publishing credentials
expired before that composed commit was published. Ordinary GitHub API writes
recreated the reviewed commits with identical source trees and corresponding
ordered parents. API-assigned commit metadata changes their Git commit SHAs.
The tree-equivalent published source is
`3349af525478d74fb13b87e8c2dc32939d3c6cbb`.

The later local `d61ef3204bc0edd2ea14579a327a954bd2075219` has the same source tree as published
`64d8c6df18d4c87f0a1cc06edc8353ac6cbb9508`, tree
`df72714e12de271ab5790959de2dbe3a891e639b`. Its sole change after the CPU
source freeze is the reviewed browser harness readiness line. All production
bytes remain identical. The separate review branch is
`review/model-development-composed-source-0319`; later evidence-only commits
may advance it. PR78 remains the authority for final composed checks and merge.

[The manifest](original-to-published.json) records all 12 original-to-published
commits, exact tree hashes, both ordered parent lists and published metadata.
The two independent review receipts establish source-plan and actual remote
publication correspondence. The 20,436-byte [original Git bundle](original-local-commits.bundle),
SHA256 `b536e9dbb2dc7e75500774e67f5a9f91d18f03029b66525494cb9a9c70dc1219`,
preserves the original commit objects and original metadata. Its nine existing
repository prerequisites remain reachable through the published component
parents. Verify/import it in a disposable clone with those parent objects:

```sh
git bundle verify docs/plans/extension-system/reports/api-source-provenance/original-local-commits.bundle
git fetch docs/plans/extension-system/reports/api-source-provenance/original-local-commits.bundle HEAD
git diff --exit-code e1bc02a68355876ec64e5e1e272019c2018b5c63 3349af525478d74fb13b87e8c2dc32939d3c6cbb
git diff --exit-code d61ef3204bc0edd2ea14579a327a954bd2075219 64d8c6df18d4c87f0a1cc06edc8353ac6cbb9508
```

These are source correspondence records, not new training, numerical or CI
proof. Original failed qualification and later same-Run recovery receipts retain
their own provenance. The rejected temporary write-enabled publishing workflow
was never installed or executed; it is absent from this bundle and publication.
