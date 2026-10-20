# Issues

| ID | Finding | Owner | State / disposition |
| --- | --- | --- | --- |
| V1 | Shared API/Run/UI hooks overlap PR102–110 | parent/repository lead | resolved: parent relayed explicit lead-approved hunks; reliability83a1e128 composed without conflicts |
| V2 | Initial PostgreSQL/runtime absence | environment/parent | resolved for local tests after parent clarified disposable setup scope; PG17.11 and pinned CPU runtime provisioned under /tmp; actual direct-query tests pass |
| V3 | General results and saved view revisions are later milestones | visualization owner | preserve immutable result boundary; no early persistence engine |
| V4 | Normal Run loader swallowed access denials and skipped cleanup after identity became null | Runs/visualization | resolved: propagate401/403; generation/session-aware cleanup; actual browser revokes at detail/predictions/model-evidence boundaries |
| V5 | Isolated strict CSP did not establish deployed policy | renderer/host | resolved: scoped /workspaces policy before assets; actual browser asserts no runtime code generation or unexpected violations; existing inline CSS remains allowed |
| V6 | Dataset selector accepted input before initialization during pinned asset loading | workspace host | resolved: initial markup disabled; existing initializer enables after setup |
