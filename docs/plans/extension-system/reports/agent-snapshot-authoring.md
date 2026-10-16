# Negotiated snapshot discovery and bound-source authoring

Status: implemented, locally verified and independently source-reviewed; final
composed CI and real CPU qualification remain separate acceptance gates. Base:
`afc45dc50530c4b6bfcdf1f2d8c2f2361e2837bc`
(`integration/model-development-extension-base`). The integration lead owns all
merges and composes this branch with the separate canonical package UI repair.

The accepted agent workflow previously lacked snapshot discovery/opening and
ordinary-agent project-v2 source authoring. Owner HTTP could prepare these inputs,
but an ordinary AgentClient could not discover/open the same immutable snapshot
or publish its captured Model. This change adds bounded selected
`project_snapshots.list/get/open` v1 contracts and explicitly versions static
bound authoring as `recipes.inspect/3`, `models.publish/2`,
`graphs.create_external/2`, `graphs.preflight_external/2` and
`studies.prepare_trial/2`. HTTP, generic CLI and official MCP share that registry.

Current inspect/edit authority, pinned root identities, no-follow bounded reads,
exact source/manifest integrity and immutable capture owners remain authoritative.
The selected HTTP header alone permits the new boundary. Earlier selected
versions retain owner-only fresh project-v2 inspection/capture. Verified prior
Model publication and exact Trial-receipt replay preserve baseline current
authority and perform no new capture. Unselected owner browser routes,
legacy project-v1 shapes and legacy discovery are unchanged. Study creation,
budgets, continuation/approval and capture reconciliation remain owner-only.
No execution, grant, reservation or admission operation changes.

Compatibility verification compared all **92 existing contracts across85
operations** against the exact base: every SHA256 remained equal. The private
baseline hash manifest SHA256 was
`f1615aeeab9e80f9594a69ffdd632a698f5e4f77874860c9693cd519d2cf6d49`.
The frozen legacy digest remains
`cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8`.
Capabilities encode to386,670bytes within the unchanged1MiB limit.

Verification uses a fresh isolated PostgreSQL catalog and the existing hash-locked
optional agent environment (MCP1.30.0). `test_agent_project_snapshots.py` is covered
by the existing mandatory `test_agent_*.py` CI step. Only the official MCP case
requires its optional SDK; the ordinary HTTP cases remain in the base suite when
PostgreSQL is configured. No workflow, dependency, timeout or assertion is weakened.

The new tests cover bounded closed arguments; ordinary-agent discover/open/get;
valid, invalid and unavailable declaration siblings; explicit v1 projection;
unchanged legacy/old-version refusals; captured Model publication; graph creation,
preflight and Trial preparation; owner-only Study controls/reconciliation;
wrong selected contract/hash; missing edit, unknown root and credential revocation;
and actual CLI/official MCP read parity and revocation. Static preparation forbids
`subprocess.Popen` and checks zero added Runs, grants, consumptions or reservations.

The positive static graph/preflight/Trial case captures deliberately non-runnable
test runtime bytes. It tests capture and authoring contracts only. It does not
qualify PyTorch, NumPy, CPU execution, sandboxing or numerical output. The lead's
separate main505 operator must perform the real owner-budgeted SDK CPU admission
on the reviewed composed source and retain its actual receipt before acceptance.

Existing owner regression: **42passed,1explicit private actual-runtime skip**
(`test_extension_bound_api`, `test_extension_bound_http`,
`test_extension_http.ExtensionHTTPTests`, `test_extension_bindings.ExtensionBindingTests`
and `test_extension_bindings.BoundExtensionRecipeTests`). No claim is made that
the skipped hardware/runtime qualification ran. Historical CPU source/receipts
and frozen E2/E4 branches remain unchanged.

Independent source review caught and corrected a legacy-version revision race:
trusted boundary callbacks now authorize the exact chosen draft/graph before new
capture, while native prior-publication/receipt lookup retains baseline replay.
A complete caller audit also preserves the old fresh-source boundary on
`graphs.validate/1` and `runs.submit_external/1`; neither gains a new version.
Their refused v2 calls are tested before temporary capture or Run mutation.
Existing complete-Study composition/grant requirements remain mandatory.
Official MCP test sessions use an explicit30second protocol read deadline.

Terminal verification on stable production `06ebaf2` at test head `f68678c`:

- **75passed,0skipped**,326.715s: new15-case snapshot/authoring suite plus existing
  Model, selected HTTP, bound HTTP, Study and project CLI suites. This includes
  official MCP/CLI parity and existing real neutral-process custody/grant tests;
  those neutral fixtures establish no numerical CPU qualification.
- Fresh base environment without MCP: **14passed,1optional SDK skip**,83.607s.
  All ordinary HTTP and registry cases execute; only the official SDK case skips.
- Root/P2 requested an explicit1MiB reserve for the tiny non-runnable static
  fixture so their environment can run it without a test-runner wrapper. That
  test-only followup **passed1/1**,7.797s. The75-case run passed the same case
  with the original6GiB default. Production and CLI defaults remain6GiB;
  measured capture-byte accounting, owner/quiescence checks and actual runtime
  qualification are unchanged. The followup was independently reviewed.

[Machine verification](agent-snapshot-authoring.json) retains exact terminal logs
with SHA256s, interpreter/package versions, production source hashes and the
92-contract baseline. Independent source/complete caller review is
[clear](https://github.com/MrScripty/Tuldok/pull/86#issuecomment-6207075507), including
two independently run pure registry tests. Superseded runs that overlapped source
corrections correctly refused changed host hashes; earlier incomplete negative
arguments were also corrected. Those failed logs remain private and are excluded
from the passing results above. No production source changed during the final
successful combined run. Hosted CI is still pending; no main505 CPU execution or
final product acceptance is claimed here.
