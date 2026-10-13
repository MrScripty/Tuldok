# Catalog actors and admitted continuations

Every domain operation requires an explicit catalog actor context. Localhost,
a Dataset constructor and a background thread do not imply owner authority.
`Access.bind(token)` resolves a stored SHA256 credential hash and binds a
ContextVar; nested contexts restore their predecessor and threads do not inherit
an actor. Each admission checks catalog identity, expiration and revocation.

The owner has inspect, edit, execute, cancel, freeze, approve-review,
approve-execution, expose-holdout and admin scopes. An owner may issue an agent
bearer with inspect plus selected edit, execute, cancel, freeze and
expose-holdout scopes. Agents cannot issue credentials, approve human review or
approve execution. Current execution starts remain owner-only even when an
agent has execute; bounded approved agent execution is deferred to P3b.

## Local owner login

After creating or explicitly upgrading the catalog, stop unauthenticated old
clients and run a local administration command:

```sh
python access.py bootstrap --data ./dataset --out /private/new-owner-code
python access.py login --data ./dataset --out /private/renewed-owner-code
```

Bootstrap refuses an existing owner; login explicitly renews local owner access.
Both create a new exclusive mode-0600 file containing only a one-time code,
flush it and its parent directory, and never print the code. No HTTP endpoint
can mint these login codes. Existing files are refused. Login codes expire in
10 minutes. Atomic exchange consumes a code once and creates an eight-hour
owner session. Agent credentials default to one hour and are bounded between
60 seconds and 30 days. Logout revokes the current credential; owner revocation
acts on a credential ID. Database/filesystem administrators remain trusted.

HTTP exchanges return a session cookie; the transport enforces origin checks
and binds requests before protected body processing. The UI keeps session
authentication in the HttpOnly cookie, never URLs or browser localStorage.
Bearer clients may explicitly bind issued credentials. Identity responses contain
only catalog, actor and credential IDs, kind, label, scopes and expiry.

## Transaction and audit custody

`@authorized(scope, action, owner_only=False, target=None)` checks before calling
the domain owner and never creates an implicit transaction. The owner retains
its existing lock, transaction, savepoint and filesystem rollback semantics.
Successful mutation evidence is written by `Access.audit` in that same
transaction. Denial evidence is written after domain rollback, with one audit
per AccessError; anonymous failures have no actor. Audit details contain IDs,
revisions and request digests, not raw credentials, token hashes or provider
secrets. Audit/admission rows are append-only through the application API.

## Closed asynchronous work

An owner admits a job inside its mutation transaction using
`admit_job(kind, job_id, request_digest, effects)`, receiving a unique admission
ID for this exact attempt. The job document stores that ID. Effects are a
bounded map from action to exact target IDs (or explicitly declared null),
never wildcard capabilities. A resume/retry gets a new receipt.

A worker enters `_job(kind, job_id, admission_id, request_digest)` only after
matching its frozen input to that digest. `require_job` checks that exact bound
receipt without owner fallback. A previously admitted job may finish its bounded
effects after credential revocation; it cannot start unrelated work, use
authentication effects, approve review/execution or exercise owner-only actions.
Existing jobs without receipts may be interrupted by private `_reconcile`
startup/shutdown custody, which permits inspect/cancel only. Reconciliation
cannot resume work, edit ordinary records or assume owner approval.

`tests/test_access.py` verifies context isolation, cross-catalog refusal,
revocation/expiry, concurrent one-use exchange, agent scope limits, denial
rollback evidence, exact closed receipts, system restrictions, private CLI files
and schema-6 upgrade/schema-7 backup restoration. This stage does not claim
provider-process containment, approved agent execution or remote deployment.
