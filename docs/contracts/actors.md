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
approve execution. Existing CPU, integrity and provider execution starts remain owner-only even
when an agent has execute. The dedicated external-Run path below admits an
agent only with a matching one-use material approval.

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

## One-use external execution approvals (schema 8)

`require_external_submission()` checks a live credential with inspect and
execute scopes. It does not grant execution itself. The existing general
execute guards and `admit_job` remain owner-only. Only the dedicated external
Runs owner may compose this check with approval consumption.

`grant_execution(material_sha256, consumer_actor_id, ttl_seconds=600)` requires
owner approve-execution authority and creates a new immutable grant identity.
The consumer must be an actor in this catalog; TTL is 60–3,600 seconds. Runs
first verifies the exact previously reviewed material digest, which covers the
project/graph, captured source/runtime/input identities, parameters and declared
permissions/resources. Runs retains matching material evidence. Access owns
actor/digest binding and lifetime; it does not interpret recipe semantics.

`revoke_execution(grant_id)` serializes against consumption by locking the
grant row. Repeating revocation is harmless. A consumed grant cannot be
revoked into reusable authority: cancel its admitted Run instead. Credential
revocation and expiry still deny new submissions independently of grant state.

`_consume_external_run(grant_id, material_sha256, run_id, request_sha256)`
requires the caller's existing Run transaction. It locks the grant, checks
exact catalog/actor/material, unrevoked/unexpired state and absence of prior
consumption, then rechecks live credential authority after waiting for the
lock. It atomically writes a consumption receipt, an existing-kind `runs`
admission with only `runs.update` for this Run ID, and actor audit evidence.
It returns the admission ID; the caller inserts the Run before committing.
Rollback restores the unused grant. Unknown commit acknowledgement never
refunds it or authorizes another attempt.

Runs reconciles its existing request key against both consuming actor and exact
request digest before consuming another grant. A matching committed attempt is
returned even after grant expiry; changed actor/digest conflicts. Retry requires
a fresh grant. Owner submit may create and consume its own approval in the
same transaction only against the exact previously reviewed material digest.
Workers use the retained closed admission and may finish bounded effects after
credential revocation; they do not receive approval/admin or owner authority.

Schema 8 adds `access_execution_grants` and immutable
`access_execution_consumptions`, retaining the exact schema-7 definition.
Complete backups retain unconsumed, revoked and consumed grants with original
expiration and identity. Restoring a pre-consumption backup is a privileged
catalog recovery operation, not a mechanism for refunding live approvals.

Approval authorizes a launch; it does not establish a sandbox. Same-UID code
retains effective filesystem/network authority unless separately restricted.
Reviewed material must disclose those permissions. Source/runtime capture and
verified descendant drainage establish their specific identity/lifecycle
contracts, not filesystem or network confinement.

`tests/test_execution_approvals.py` proves exact actor/material matching,
legacy owner-only behavior, TTL/revocation, two-connection consume/revoke races,
transaction rollback, lost commit acknowledgement with retained Run receipt,
closed continuation and schema-7/8 migration/backup custody.

## Finite model studies

Study create/save/continue remain owner-only. An inspect/edit agent may prepare
exact model/trial material; it cannot acquire built-in execution permission from
that preparation. External study admission retains current inspect+execute and
one-use exact actor/material grant checks, atomically with its reservation/Run/
audit. Stop requires inspect+cancel and closes the epoch before child cancellation.
Unknown custody remains fenced. Negotiated owner-only operations advertise their
authority and still reject agent attempts. See [model development](model-development.md).
