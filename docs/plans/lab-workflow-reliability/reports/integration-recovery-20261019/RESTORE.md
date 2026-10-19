# Task recovery checkpoint

Clone the existing authorized repository branch:

```sh
git clone --single-branch --branch checkpoint/lab-integration-20261019 https://github.com/MrScripty/Tuldok.git Tuldok-recovery
cd Tuldok-recovery
git fetch origin docs/lab-workflow-reliability-plan
```

Use normal configured GitHub authentication. This checkpoint contains no credentials.
Verify every evidence file against `manifest.json` using SHA-256 before use.
The checkpoint source parent is the unmerged composed PR89/90 dependency tree
`76d3c6a2ec46f36bb5dee5f2d40d1ddf4d017114`, not main.
PR89 repair `cd5c029a6d4bde8a570064bac6687cb17394a1ac` and prior integration
repair commits are reachable in that history. Create new implementation branches
from the recorded source parent, keeping this evidence checkpoint separate.
The independent PR91 plan remains at
`b446d9a19dbd553b80bf9f3af574b8b34ddbd5cb` on its own remote branch.

Remote PR and CI state may have advanced: recheck exact heads, results and merge
status before any publication or integration. Old failed or skipped gates are
not acceptance. Retain all unrelated branches/worktrees; their inventory here
is preservation evidence, not authority to modify or delete them.

## Restore the separately published M1 implementation

The manifest records the exact later implementation head and branch. Fetch the
recorded branch from the same repository, verify that the recorded commit is
present, and create the recovery worktree from that exact SHA. If the feature
branch was safely deleted after a merge, fetch main and establish the recorded
commit's ancestry there before using it. Do not substitute the latest tree for
the recorded source without reviewing its changes. This checkpoint and the
implementation/plan branches remain separate; fetching is not product merge
or acceptance. Check fresh CI and independent-review disposition after restore.
