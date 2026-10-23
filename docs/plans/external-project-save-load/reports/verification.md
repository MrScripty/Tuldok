# Planning verification

Scope: documentation in `docs/plans/external-project-save-load/` at application baseline `133d53c0e2985a6559ba9cebd7d4a9f530051f06`. Standards baseline is `5bce3110fc64d61ff8b4f79468184bd6295855d5`. This record concerns plan structure, source reasoning, links and scope only. It does not satisfy product A1–A9 or claim runtime validation.

## Material subject and result

| Check | Actual result / limit |
| --- | --- |
| Source/standards baseline | Remote main and local fetched source agree on the revisions above. Checked workspace ancestry, tracked tree and checkout skill paths; no applicable AGENTS/skills. Source facts are pinned in the baseline report, not inferred from older plans. |
| Exact upstream plan structural function | PASS for one selected plan (nonzero): `validate_plan(plan_text)` returned `None`, using unchanged standard-library AST functions/constants/helpers from the source below. Initial bold probe prefixes were rejected; canonical plain prefixes repaired that markup. Structural validity does not prove semantics. |
| Relative links / pinned sources | PASS: every relative Markdown target exists; every immutable GitHub source link resolves to a file object in the recorded Tuldok/standards revision. Code fences excluded from link parsing; balanced fences checked. Source-object resolution does not certify remote publication or product behavior. |
| Independent complete review + changed findings | CLEAR after three material findings and one bootstrap detail were resolved and re-reviewed. Exact final subject hashes below match the reviewer's observations. See independent-review.md for scope/dispositions. |
| Whitespace, staged scope and sensitive-file review | PASS: `git diff --cached --check`; staged paths consist only of the six Markdown documents in this plan directory. Index bytes match the reviewed authored files; no product/config/catalog/binary/credential files are staged. |
| Original checkout and standards | Preserved at their original recorded HEADs with clean status. Planning worktree is isolated on its private named branch. No push/PR/merge or standards mutation. |
| Product/runtime tests | Not run. This is a Markdown-only task. Filesystem/PG/process/CLI/SDK/MCP/browser A1–A9 remain prospective; no runtime, power-loss, scientific or migration result is claimed. |

Final reviewed material SHA256:

- `plan.md`: `d6d3832a494a44aebae15bed20748a6d5b90dfa98919d315a179abae02d60b4d`.
- `reports/baseline-and-standards.md`: `67a0d17727c1467cc1c979c0147462156c47a257dd134ffff6be3bbee9071911`.

Supporting review/ledger/verification records do not alter this material subject. There is no evidence-volume target, fixed campaign count, all-suite rerun, or exact-HEAD re-review after unchanged bookkeeping.

## Reproduction and checker provenance

Canonical structural checker:
`tools/standards_verifier/standards_verifier/checks/plan_contract.py`
at Coding-Standards `5bce3110fc64d61ff8b4f79468184bd6295855d5`.
File SHA256: `c7266c0564b9ee02944fc4eb12d66cc20d604fd4ddb7f051ed77d01e9fe4466e`.

The same bounded loading method used by earlier repository plan checks avoids unrelated aggregate package initialization. Parse its Python AST, retain original Assign/FunctionDef nodes before the first ClassDef plus `re` and future imports, then execute those unmodified nodes and call `validate_plan` on this exact plan. No checker condition or expected value was weakened. The local disposable helper `/tmp/check_tuldok_external_plan.py` ran that function, checked all relative targets and pinned source objects with `git cat-file -e REV:PATH`, verified balanced fences and emitted the material hashes. It adds no production tool or permanent verification framework.

Final documentation commands from the planning worktree:

```sh
python /tmp/check_tuldok_external_plan.py
git diff --cached --check
git diff --cached --name-only
git diff --cached --stat
```

Preflight identified the exact worktree, original source/standards refs, six Markdown paths and one structural plan selection before interpreting results. The staged review compared index bytes with the reviewed files and checked the plan/source report hashes. Required unavailable product environments are not substituted by these documentation checks. No Standards Engine application MCP is exposed, so no Engine certification is claimed and no authoring bypass was attempted.

## Deliverable and resources

Local branch: `plan/external-project-save-load-20261022`.
Worktree: `/workspace/Tuldok-project-save-load-plan`.
Only output subtree: `docs/plans/external-project-save-load/`.
Local commit: the retained named branch's head, reported in the final response; resolve with `git rev-parse plan/external-project-save-load-20261022`.
The branch head is `retained-ref`, disposition `retained`, worktree outcome `retained-protected` for user review. The user owns integration/retirement; no remote action or cleanup is authorized here. No real blocker remained to planning, independent review or local documentation commit.
