# External project authority

The external project directory owns scientific records. PostgreSQL is a disposable
projection in the explicit project-file mode. The legacy catalog mode retains its
existing authority until an explicit future extraction; registration snapshots
are not Save/Save As.

The implementation follows the [reviewed plan](../plans/external-project-save-load/plan.md),
initially committed as `2c9c9b098c9f1c4c2557c58818574ebdbc1e7d41`, based on
Tuldok `133d53c0e2985a6559ba9cebd7d4a9f530051f06`. Applicable standards were
inspected at Coding-Standards `5bce3110fc64d61ff8b4f79468184bd6295855d5`;
[the source report](../plans/external-project-save-load/reports/baseline-and-standards.md)
pins links and decisions. The implementation ledger records subsequent evidence.

`ProjectStore` owns rooted filesystem access, immutable record publication and
the atomic checkpoint. `ProjectText` reuses Workbench's text policy inside an
outer SQL transaction, publishes the complete validated canonical revision before
SQL completion, and returns only after both boundaries complete. Failure after
canonical publication preserves the committed files and fences the projection
until reconstruction. SQL rollback cannot roll back canonical history.

`ProjectWorkspace` owns selection, opaque request binding, local authorization,
projection lifetime and admission of supported operations. Each open uses a new
physical projection ID, while the canonical project UUID stays stable. A clone
cannot alias the originating installation's SQL schema. Access credentials and
current grants belong only to the installation control catalog.

M1 deliberately instantiates no Dataset, Run, Job, generation or dependency
installer owner in project mode. Its only scientific family is authored text
with annotation history. All unfinished domain routes are fenced before dispatch
and unavailable in capabilities. This restriction is temporary under M2/M3 of
the plan, not acceptance of the full requested save/load capability.

The supported publication platform is a local Linux/POSIX filesystem honoring
file and directory fsync, anchored no-follow access, advisory exclusion, and
atomic no-replace rename. The representative qualification used overlayfs and
PostgreSQL 17. It does not establish power-loss survival on storage that ignores
fsync, or support for network filesystems or Windows.

Open validates canonical bytes and rebuilds inert text projections. It never
imports project Python, executes scripts, installs dependencies, downloads model
weights or regenerates data. Domain integrations remain project scripts. Later
families must preserve historical IDs and hash inputs, separate historical proof
from current permission, and declare unique/generated artifact dependencies.
