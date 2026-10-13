# P7 source checkpoint: permission-preserving restore

The existing PostgreSQL/artifact transfer now preserves file modes, applies
directory modes after children, and checks resumed/completed restore permissions.
The retained version-1 byte receipt format is unchanged. Old byte-only receipts
do not authenticate original modes. Runtime manifests and historical Run paths
are never rewritten. Canonical contract: [local storage](../../../contracts/local-storage.md#backup-permission-preservation).

Independent review found and resolved read-only partial-cleanup failure,
intermediate symlink traversal, descriptor-acquisition leaks and root-name
replacement races. Cleanup only touches the invocation-owned private partial
backup through retained descriptors. Uncertain identity retains the partial and
the original error with a diagnostic note. It never widens source or resumable
restore permissions.

Validation: the owned metadata/runtime modules passed 37 tests in245.229s before
the final cleanup refinements. Final eight affected tests passed in9.081s,
including descriptor failure, symlink and directory replacement, source-mode
mutation, partial failure and a small real backup/restore with cold runtime
inspection. Counts overlap; they are not45 distinct tests. Small executable
fixtures do not qualify the actual scientific catalog or a model. Independent
final source review found no remaining blocker in the admitted scope.

The staged Python qualification procedure covers raw SQL/sequence/schema parity,
file bytes/modes, custody drainage, a separate-DB SQL probe, cold restored runtime
inspection and completed artifact reads. The portable browser procedure covers
loaded Data/Pipeline/Run views and all89 authenticated output hashes. Both are
source-prepared only. Actual backup/restore, final regression and hosted CI remain
pending; P7/G7/G8 are not accepted by this checkpoint.

The qualified source catalog is untouched. Measured capacity cannot currently
hold source+backup+restored copies with reserve. Any two-copy fallback requires a
complete independently verified backup, successful separate-DB SQL probe and an
exact task-owned source disposition approved by the integration owner. No source
deletion is authorized by this report.

The later explicit user instruction authorizes merging qualified PRs in dependency
order. This supersedes earlier no-merge planning instructions; it does not
authorize merging incomplete/failing work or deployment. PRs38–42 are merged;
PR43's actual-packet gate remains an integration blocker at this checkpoint.
