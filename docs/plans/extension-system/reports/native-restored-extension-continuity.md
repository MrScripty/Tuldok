# Native restored extension continuity

The optional `restored_checks` branch of `tests/browser_field_evidence.cjs` is a read-only browser journey for a disposable, already restored catalog. It does not disable or remove a provider, create a Project snapshot, prepare a Model/trial, approve material, or admit a Run. The stopped backup/restore owner prepares the two refused snapshots and the unrelated completed built-in Run first. The original catalog and source packages are outside this journey.

The real input receipt retains the usual `catalog_path`, `run_id`, `project_roots`, and `expected_fields`, plus:

```json
{
  "restored_checks": {
    "disposable_restored_catalog": true,
    "refusals": [
      {"mode": "disabled", "project_id": "actual-saved-id", "recipe_id": "actual-recipe-id"},
      {"mode": "removed", "project_id": "actual-saved-id", "recipe_id": "actual-recipe-id"}
    ],
    "retained_runs": [
      {"label": "a", "run_id": "actual-a-run-id", "expected_fields": [{"field_id": "raw", "stage": "train"}]},
      {"label": "b", "run_id": "actual-b-run-id", "expected_fields": [{"field_id": "raw", "stage": "raw_inference"}, {"field_id": "corrected", "stage": "boundary_enforcement"}]}
    ],
    "unrelated_run_id": "actual-completed-built-in-run-id",
    "unrelated_graph_id": "actual-saved-graph-id",
    "unrelated_release_id": "actual-frozen-release-id",
    "unrelated_recipe_choices": ["exact ordered allowed_recipes from the release owner"]
  }
}
```

These placeholders describe test input structure and are not successful evidence. The restored database DSN is supplied through `TULDOK_DATABASE_URL`, never retained in the receipt.

Native keyboard activation opens each current B recipe inspection. The real refusal must match an independently read selected-contract owner response; the dialog must contain no configuration form, preparation, approval, admission, or cached trial review. Both historical source Runs then reopen with their exact retained field/stage identities and checkpoint lists. The unrelated built-in Run must remain completed with downloadable artifacts matching their whole-byte hashes, and its saved graph and exact owner-projected create-recipe choices must remain available. No creation or execution button is activated.

The journey compares all ten Model/graph/material/Study/trial/grant/admission/Run table counts before and after, preserves all Run IDs, and rejects every browser POST other than a model-evidence read query. Existing stale-response and explicitly labelled 403 transport-substitution checks remain separate from these actual provider refusals. Captures at 1440 and 390 pixels retain the real refusal and continuity surfaces. Application source changes are outside this tests-only adaptation.

Syntax and diff checks pass. An independent read-only review caught synchronous saved-graph select replacement; the helper now reacquires and asserts real focus after each native option change and waits for that exact intermediate selection. Actual restored-catalog acceptance remains pending the stopped backup/restore owner's fixture and service handoff; this document records preparation only.
