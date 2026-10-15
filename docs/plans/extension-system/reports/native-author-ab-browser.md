# Native A/B browser gates

These actual-transport browser journeys are prepared for the final authored A/B sources. Syntax and existing controlled field/author lifecycle checks pass. No actual source Run or browser acceptance is claimed by this adaptation; admission remains held until the main operator/source freeze and review are complete.

`tests/browser_extension_model_author.cjs` uses `TULDOK_BOUND_MODEL_BROWSER_RECEIPT` with the real `catalog_path`, complete `project_roots`, `project_id` and `recipe_id`. Optional `model_controls`, `trainer_controls`, `inputs` and `budget_controls` choose real native form values; no successful API result is injected. The default full journey prepares an exact Model/graph/Study trial, requires separate native review/approval and explicit Study admission, checks one charged attempt, and waits for automatic native retained fields. Its `--inspect-only` mode stops before grants/admission. Full mode must not run during the current source hold.

The source receipt can include `expected_fields`, an exact list of `{field_id, stage}` pairs derived from the reviewed recipe's `model_evidence.fields`: `field_id` is each field's `id`, and `stage` is its `contract.output.stage`. This is an expected identity assertion, not field data or a callback. For corrected B:

```json
{"expected_fields":[
  {"field_id":"raw","stage":"raw_inference"},
  {"field_id":"corrected","stage":"boundary_enforcement"}
]}
```

The native author receipt forwards those expectations into its emitted `field-source.json`. `tests/browser_field_evidence.cjs` reads this file through `TULDOK_FIELD_BROWSER_RECEIPT` or an equivalent receipt for an existing actual qualified Run. It verifies that the actual retained field/stage identity set matches the reviewed source, inspects all checkpoints, fixed members and orthogonal axes, and compares native numeric probes to exact owner query results.

The field journey also physically selects each actual declared field/stage using native Home/ArrowDown/Tab keys, asserts real control focus and completed loading, then captures each field pair at 1440/390 in light and dark preferences. It records selectors, stage/field identities and separate prediction/reference values. It derives no residual, target, MSE, inference or physical operator. The existing shared physical/display scale, standalone/no-frame, unsupported test/physical acceptance, delayed navigation and labelled 403 transport-presentation checks remain intact. Before/after Run IDs and the operation-route journal enforce read-only field inspection.

Source-owned private-QA rights and the absence of numerical/physical acceptance remain explicit. The independent frozen oracle on actual downloaded retained artifacts is a separate gate. Existing prepared inert fixtures or the separate unadmitted B compatibility catalog cannot substitute for actual source Run evidence in the final common catalog.
