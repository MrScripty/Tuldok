# Classification export-only Runs

Image, text and audio classification releases offer two explicit choices:
existing training recipes and `image_validate_export`, `text_validate_export`,
`audio_validate_export`. Training stays the default. Export-only recipes have
exactly `release → validate → publish` stages, no parameters and version 1.
They use existing strict frozen classification readers, without a second
archive format validator, training interpreter, model worker or model probe.
Readers still enforce their existing frozen contract, including split, label,
family, review and native payload requirements. Export-only does not weaken
these rules or admit arbitrary canonical mixed-task archives.

## API and ownership

Pipeline definitions list the new recipes with versioned typed ports.
Release inspection includes `allowed_recipes`, an ordered list containing the
existing training ID followed by its export-only ID; `recipe` remains the
training default. Mesh and sequence releases advertise only their respective
integrity recipe. Graph creation takes the explicit `recipe` field. Existing
image training documents without a recipe field and their execution digests
are unchanged. No stored five-stage graph is relabelled or migrated.

`Pipelines.inspect_release(id, recipe=selected_recipe, private=False)` verifies
the release against the selected reader and refuses task mismatches. Export-only
inspection returns `result_kind=release_validation`, the selected `recipe`, and
`validation_summary` containing `schema_version`, original `format`, `kind`,
`record_count`, `split_counts`, `class_vocabulary`, and the integrity-only scope.
Validation, snapshot admission, execution, retry and source download all carry
the selected recipe; none silently fall back to the default training recipe.
The default public release listing remains suitable for either choice.

`release_validation` owns integrity report identity and reuses its existing
closed report writer/verifier. Runs owns admission, queue capacity,
idempotency, cancellation, artifact publication, custody and reopening.
Execution requires the imported in-process definition closure to match disk
and binds it into the validation token. Changes after admission fail stale;
changed release bytes fail their frozen identity proof. The training runtime
is irrelevant to integrity availability.

## Results and limits

An export-only attempt publishes `validation-report.json` and
`artifact-manifest.json`; source `release.zip` download retains its exact
original bytes and content identity. Reports identify the selected export
adapter and graph, and describe integrity counts. They produce no model,
predictions, metrics, quality or untouched-holdout claims. Prediction and
expose-test operations reject these attempts and create no exposure events.
Existing prior exposure facts remain visible as history, not as a new event.

Cancellation during reading is observed before publication. Retry uses a fresh
attempt and repeats graph, definition and source checks. Restart never replays
an interrupted in-process validator automatically. Retained completed reports
use their admitted identities and existing custody checks; installed recipe
additions do not rewrite past graphs or results.

## Evidence

`tests/test_export_runs.py` exercises actual PostgreSQL image, Unicode text and
PCM audio frozen releases. Each modality covers explicit choice, cloning,
layout editing/save, validation, completed report and exact source download,
reopen, invalid connection, wrong modality, stale graph/token/definitions,
changed frozen bytes before and after admission, cancellation during reading
and fresh retry. The real export flow deliberately points the training
interpreter to a nonexistent file and makes model probe/worker calls fail the
test. It verifies no model metrics, predictions or exposure events.

Run the backend gate with the configured local PostgreSQL connection:

```
python -m unittest discover -s tests -p test_export_runs.py -v
```

Existing Pipeline, mesh and sequence Runs tests remain regression gates. UI
selection, compact version-difference presentation and embedded editor breadth
have separate browser evidence. Backend tests alone do not accept those paths.
