# Local QA and fixture inputs

Python, controller, browser and consumer gates are registered in `.github/workflows/tests.yml`. Provision dependencies separately; the runner never installs packages. The application requirements include NumPy2.5.3 and require Python3.12+. Node22+ with WebSocket and Chromium are needed for browser tests; set `BROWSER` to the executable.

The scoped, no-training regression command excludes five separately registered consumer/combined workflows:

```sh
python scripts/qualify_text_classification_local.py --python /path/to/consumer-venv/bin/python --timeout 240 --only '^(?!node tests/(?:check_text_corpus_consumer|check_image_classification_consumer|browser_preferences|browser_instruction_responses|browser_combined_workbench)\.cjs$)'
```

That scope contains104 of109 registered gates. It includes Python discovery, current controller/real browser checks and actual NumPy/NPZ consumption. Optional installed Torch2.8 CPU is used only for explicit list-collated DataLoader iteration in the native sequence gate. The excluded gates are not qualified by a scoped run; some separately exercise trainer or other neural consumer behavior. Do not interpret a previous pass or authored fixture as current runtime evidence.

An optional `TULDOK_NATIVE_LEGACY_RELEASE` path lets the native gate read an existing frozen release with its exact pinned hash. This is a data input, never an old report copied as a new result. A configured missing or mismatched input fails; no alternate source is selected. Legacy packets without family-context proof are admitted only with one populated split and a visible limitation.

Every invocation writes fresh ignored `build/qa/qualification/run-*` outputs. Each gate gets its own subtree; previous reports/runs are never scanned or recaptured. `--report-root` permits only ignored build/output containers. `--resume` needs an exact existing run and unchanged source plus complete matching direct artifacts. `TULDOK_SOURCE_ROOT` is pinned to this checkout. Standalone tests accept `TULDOK_QA_OUTPUT_ROOT` outside source or within ignored build/output; aliases into tracked fixtures/docs are rejected before child startup. Screenshots use JPEG85. Authored source images and pixel/hash-dependent inputs stay lossless PNG.

`historical-artifacts.json` retains only11 lossless fixture paths, sizes, hashes and original-source locators. The unchanged QA regression reads that path. Its name is retained for compatibility; generated artifacts, outcome indexes and review histories are not present. [Fixture provenance](../fixtures.md) identifies required source inputs. No generated datasets, ZIP releases, screenshots, logs, checkpoints, PDFs or qualification receipts belong in Git.

The unregistered historical `capture.cjs` replay requires its exact previously published cleanup checkout and is omitted from this current handoff. Use current registered browser tests here; source-only cleanup does not rewrite or erase inherited public history. Existing checkouts and retained originals remain separate.

General COCO qualification uses actual pycocotools2.0.11 and torchvision0.23.0 bbox readers, with independent strict geometry/ID/hash checks before permissive COCO indexing. Provision `tests/coco-consumer-requirements.txt` separately (CPU Torch wheels are sufficient); optional `COCO_CONSUMER_PATH` points to an isolated installed package directory. Neither gate downloads packages or data. `check_general_coco.cjs` covers multiple objects/categories, reviewed negatives, native canonical roundtrip and an all-negative train-only profile. `browser_general_coco.cjs` exercises fractional/subpixel authoring, explicit review, exact saved selections, export and a second scratch owner's native import/review/export. No model, optimizer, mask conversion, evaluation or training executes. Exact consumer source/package pins and fixture limitations are retained in `tests/fixtures/coco-consumer-pins.json`.

Multi-source instruction authoring adds `browser_grounded_instructions.cjs` and the composer syntax gate to that scope. Its downloaded ZIP uses the existing instruction consumer in `--reader-only` mode: pinned source checks plus actual Datasets JSON reading and exact passage evidence, with no tokenizer/model/trainer construction. The five separate neural/combined gates remain excluded. See [composition/review contract](../decisions/grounded-instructions.md).
