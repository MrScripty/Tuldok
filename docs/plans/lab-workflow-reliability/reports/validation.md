# Plan preparation validation

Subject: documentation under `docs/plans/lab-workflow-reliability/`, based on
main `300f12df6f48e028fd9379911703f7c89337952a`. These checks concern the plan,
not the proposed product behavior. All A1–A8 acceptance claims remain pending.

## Checks and evidence boundary

| Check | Actual result / scope |
| --- | --- |
| Repository/worktree inspection | Separate docs branch/worktree; unrelated work preserved; no product, runtime, catalog or workflow writes. |
| Remote baseline and dependencies | Anonymous `git ls-remote` and GitHub reads agree on recorded main/PR89/PR90 SHAs and open/unmerged dependency state. No CI or merge success is inferred. |
| Exact upstream structural validator | PASS: `validate_plan(plan_text)` returns `None` using the original AST, constants and helpers at Coding Standards `dcc56f26e884ade260770beceba2501d3746200d`. |
| Manual policy/contract application | Current plan template, eight architecture probes, acceptance-kind/environment/mode distinctions, domain ownership and explicit compatibility/recovery decisions reviewed. See [baseline and standards](baseline-and-standards.md). |
| Independent review | CLEAR after the one blocking finding and two recommendations were resolved; [independent plan review](independent-plan-review.md) pins exact material identities. Report SHA256: `b6666f6036f798cb62bead680f1ddb4cceb3049aed87358b4478d2f5de8b9d10`. |
| Relative links, whitespace and scope | PASS: all23 relative links/anchors resolve, no whitespace findings, all8 changed/new paths confined to this plan directory. Exact material hashes and actual results are in [validation.json](validation.json). Code fences are excluded from Markdown-link parsing. |
| Standards Engine application route | Unavailable: no exposed MCP; local application-purpose invocation returns exit2, `Application invocation is unavailable; use the published interface contract.` No authoring bypass/full Engine certification was used. |
| Application, catalog, GPU and scientific tests | Not run: documentation-only change; no product pass, hardware reproduction, benchmark speedup or scientific acceptance is claimed. |

## Structural checker provenance

Canonical source:
`tools/standards_verifier/standards_verifier/checks/plan_contract.py` in the
adopted local Coding Standards checkout. Source SHA256:
`c7266c0564b9ee02944fc4eb12d66cc20d604fd4ddb7f051ed77d01e9fe4466e`.
No verifier logic, constants or expected rules were changed. As in the existing
D1 plan check, load just its standard-library AST before the first checker class
to avoid unrelated aggregate package initialization:

```python
import ast
from pathlib import Path

source = Path("/workspace/coding-standards/tools/standards_verifier/"
              "standards_verifier/checks/plan_contract.py")
body = []
for node in ast.parse(source.read_text()).body:
    if isinstance(node, ast.ClassDef):
        break
    if (isinstance(node, (ast.Assign, ast.FunctionDef))
        or isinstance(node, ast.Import)
        and all(alias.name == "re" for alias in node.names)
        or isinstance(node, ast.ImportFrom) and node.module == "__future__"):
        body.append(node)
namespace = {}
exec(compile(ast.Module(body=body, type_ignores=[]), str(source), "exec"), namespace)
plan = Path("docs/plans/lab-workflow-reliability/plan.md")
assert namespace["validate_plan"](plan.read_text()) is None
```

This proves selected lifecycle/structure rules, not semantic completeness or
future implementation conformance. Independent review and explicit T1–T8
procedures cover the plan's intended meaning; future implementation requires
its own real acceptance evidence and exact candidate CI.

## Reproduction and final scope

Run the structural snippet above from the plan worktree; resolve every relative
Markdown link/anchor against its file; run `git diff --check` and full new-file
`git diff --no-index --check /dev/null FILE` (diff exit1 alone is normal); inspect
the exact staged diff and confirm every path is under this plan directory.
No permanent validator or custom test framework is added to the application.
The local disposable helper `/tmp/validate_lab_plan.py` combines these read-only
checks and emits the linked JSON, excluding self-referential validation/review/
ledger hashes from its material-subject hash set.
