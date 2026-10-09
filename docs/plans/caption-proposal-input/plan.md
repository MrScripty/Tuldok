# Correctable caption request input

Parent-authorized narrow follow-up to PR17 `4ed5466fd764e938999cca1d535e9a33379271a0`,
tree `543abea3a86036656e7e527a73ccaef12ccb70a7`. Isolated branch
`fix/caption-proposal-input-local-20261007`, worktree `/workspace/Tuldok-caption-input-local`.
Main, development, old PR17 source/evidence and classification work stay untouched.
No merge, history rewrite or manual CodeRabbit request is authorized.

Root independently reproduced valid P2: the guidance textarea allows 4,000 UTF-16
units so that 2,000 non-BMP code points fit. A fresh 2,001 ASCII-character value
passes native form constraints but RecoveryBody’s 2,000-codepoint validation was
caught as a durable-storage error before any write or POST. Correction and GET
refresh could not clear that sticky latch without a full reload.

Fresh request body validation now runs before storage mutation/failure handling.
Its error is a correctable form status, leaving no pending ID, storage entry or
POST and keeping submission enabled. The same validator retains strict reading
of stored recovery: malformed/oversized evidence still fails closed. No recovery
ID ownership, reconciliation, ambiguous404, refused repeat, history/ACK fencing,
provider contract, draft application or human-review behavior changes. The
validator preserves exact guidance rather than truncating/normalizing it.

Boundary tests cover 2,000/2,001 ASCII and non-BMP code points, mixed strings and
correction plus refresh without reload. A 2,000-emoji string has 4,000 UTF-16
units and is admitted exactly; the extra code point is rejected before storage.
Invalid previously stored guidance remains retained and blocks POST. Existing
storage read/write/remove/corruption and shared-tab ownership tests still run.
Real Chromium submits 2,001 ASCII, corrects to 2,000 emoji and admits successfully
in the same document without reload.

Narrow write set: caption controller validation, existing reload controller and
real caption browser tests, this plan/evidence. All 43 inherited workflow commands
and ordering remain unchanged. Qualify exact source through all aggregate gates
and independent review, preserve every previous report byte, then update the
existing draft PR17 under standing owner authority.

Reusable successor rule: validate fresh user input before entering any durable
storage-failure latch. Corrupt stored recovery remains a distinct fail-closed
condition; user correction must never silently discard that evidence.
