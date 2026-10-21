# Revised current-version acceptance scope

The user explicitly removed backward compatibility as a Tuldok requirement.
Existing projects must perform their own one-time migration/adaptation to the new
version. The [existing plan](../../plan.md) and its
[current acceptance procedures](../contracts-and-acceptance.md) now supersede
older compatibility obligations. Canonical client/storage documentation records
the same policy.

The intentional breaking support policy permits current project, client,
operation and catalog-format changes without old-project adapters or historical
schema/old-client preservation gates. This amendment invents no schema number,
wire change or automatic migration framework. Current declared schemas and
contracts still validate, unsupported versions fail honestly, and original data
and stopped backups must be retained for owner-led migration.

The previously completed actual old-application witness and its independent
reviews remain preserved on their original checkpoints and sealed reports as
historical, non-gating evidence. It had already reached its successful hosted
checkpoint before the user revision. Its new helper/invocation is removed from
active source; `tests/qualify_spatial_retained_runs.py` is byte-identical to the
pre-existing `cd420c44` version. No additional old-project witness is being run.
Unchanged incidental historical regression tests are not expanded by this update.

Current-version composed stopped backup/restore, immutable failed-Run meaning,
result identity, custody/accounting, candidate-promotion fences, scientific
operand meaning and no compute replay remain acceptance requirements. The
completed current-version restore and facade cost/integrity evidence retain
that scope. The facade matrix supports only its named local workloads and leaves
the individual default unchanged. Exact-head current-version hosted checks and
independent review remain merge gates. PUB-1/SCI-1 still require their genuine
original lab inputs.

The sealed earlier bookend/review reports describe their own historical subjects;
this scope update does not rewrite their evidence or imply a new test result.
