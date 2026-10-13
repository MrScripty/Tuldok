# P7 actual backup and restore qualification

Actual scientific catalog backup/restore passed on Python3.12.14 with the
permission-preserving transfer owner633b816. Final local compatibility refinement
and hosted regression remain separately recorded below. No deployment.

## Exact retained state

Source catalog UUID `d4856fe9eec74aea8b007cca029b3248`, schema8:31 SQL tables,
462 rows,21,537 files/5,281,350,158 logical bytes and23,392 tree entries.
All21 external attempts retain verified drained custody:17completed,3failed,
1cancelled. Table/schema/sequence/file/mode parity was established before any
Dataset/auth construction at the restored destination.

[Final report](p7/final-report.json), SHA256
`9f0cd5949539520b168a3087095c002b965540fc7e4c8cde3a7b942c8d69e85a`.
[Raw restore proof](p7/restore-raw.json), [independent backup oracle](p7/independent-backup-proof.json),
[committed separate-DB SQL probe](p7/probe-sql.json).

The full backup remains at
`/tmp/tuldok-p7-scientific-restore-qualification/full-backup`; receipt SHA256
`cea2a452a4c1478ab54ffd3866a85b7111da8b08ecdb9f603c0eb96483a1389c`.
Restored catalog:
`/workspace/scratch/tuldok-cpu-qualification/restored-catalog-20261013`.
Its private connection configuration is
`/tmp/tuldok-p7-scientific-restore-qualification/restore.env`; credentials are not
published. The original PostgreSQL database/schema remains unchanged.

## Measured two-copy procedure

Source+backup+restore coexistence was short2,723,254,272 bytes including512MiB
operational and128MiB additional DB/WAL reserves. After complete backup,
independent all-byte/mode proof and committed SQL probe, root independently
verified exact evidence and admitted disposition of only the task-created
source filesystem tree (device27/inode1210551). Fresh full source parity and
quiescence passed under the metadata lock before its exact removal. Original
database, verified backup, other catalogs, toolchains, owner worktrees and
failed/cancelled evidence retained in the backup were preserved.
[Exact admission](p7/source-disposition-admission.json),
[disposition result](p7/source-disposition-result.json),
[original DB proof](p7/final-original-database.json).

The old source path is absent, so restored reads cannot fall back to it.
Historical opaque Run/spec/material/custody paths and hashes were not rewritten;
no historical attempt was resumed. Current inspection generates a descriptor
for the unchanged CPU manifest at the new root.

## Cold owners and public UI

The actual captured CPU snapshot
`cc54ef199fc192b70f702e85dda70bfc8697bf3220373ae9f031afd8b237f0a7`
verified at its restored root. All156 artifacts from17 completed Runs
(3,471,725,258 bytes) and all six immutable releases matched full hashes.
Typed scientific view/history remained intact; no Runs scheduler thread started.
[Cold qualification](p7/qualify.json).

The production restored app was proven to use the distinct restore database
before owner login. Loaded Data pressure slices, saved Pipeline and completed
Run views passed at1440 and390 pixels. All89 evaluation artifacts
(3,086,837,711 bytes) matched the prior authenticated HTTP inventory. Graphs,
Run/record IDs and the reviewed record remained unchanged. Root visually
reviewed the loaded narrow slice and desktop results.
[Browser receipt](p7/browser-receipt.json),
[server DB scope](p7/browser-server-database-scope.json),
[loaded slice](p7/inspection-loaded-data-390.jpg),
[results](p7/inspection-summary-1440.jpg).

The first browser attempt passed reads/HTTP but failed logout with400 because
the new QA request omitted its required JSON body. That attempt is retained.
The exact newly issued session was revoked through authenticated Access, and
the fresh cleanup session logged out. The corrected request passed in a new
browser attempt with verified200/logout and guaranteed child cleanup. All new
QA sessions are revoked; source DB and all non-auth state remain exact.
[Session cleanup](p7/failed-browser-session-cleanup.json),
[successful logout](p7/browser-logout.json).

## Implementation and final code gates

The existing owner preserves ordinary file modes, applies directories last and
refuses contradictory resumed/completed permissions. Private partial cleanup
uses retained descriptors, guards acquisition and refuses uncertain identity.
Version1 byte receipts remain unchanged and do not authenticate historical
modes; cold runtime verification is required. Canonical
[storage policy](../../../contracts/local-storage.md#backup-permission-preservation).

The owned metadata/runtime modules passed37 tests before final cleanup
refinements; eight final affected checks passed9.081s. Final review found
a Python3.10 compatibility gap in exception diagnostics. It now uses
`sys.exc_info()[1]`, optional notes and an explicit CLI diagnostic preserving
original exception identity/arguments. Nine affected tests passed8.431s,
including legacy note capability and a tiny cold-runtime backup/restore.
Copy/mode/receipt/restore functions remain byte-identical. The API availability
is documented in [Python sys](https://docs.python.org/3.11/library/sys.html#sys.exception)
and [exceptions](https://docs.python.org/3.11/library/exceptions.html#BaseException.add_note).
[Compatibility receipt](p7/python310-compat-receipt.json). Tests ran on3.12;
3.10 grammar checks passed, but no3.10 interpreter execution is claimed.
Counts overlap. Independent final review found no concrete blocker.

Fresh hosted lifecycle/UI on the final published branch remains the full
regression acceptance gate. Both main push triggers are enabled here and in
independent PR54 to verify integrated main directly. No Standards Engine
certificate or unconfigured type checker is claimed.

This closes the actual scientific transfer/read gates within their stated
environment. Dataset-workflows A8 real positive model assistance and the
original legacy-v2 packet remain separate external blockers; authored
compatibility fixtures do not close their real-data/model acceptance.
