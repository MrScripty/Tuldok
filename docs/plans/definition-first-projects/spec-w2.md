# Implementation spec: the Map workspace, phase 2: the page, read-only

This is phase 2 of [the Map workspace plan](workspace-plan.md); [spec-w1.md](spec-w1.md) is phase 1. Section 1 of [spec-m1-m2.md](spec-m1-m2.md) (rules for implementers) applies, with the import rule as amended by [spec-m7.md](spec-m7.md).

**The reference is the mockup the owner chose and remembers:** `docs/plans/project-workspace-redesign/mockups/b-map.html` with `shared/base.css`, `tree.js`, `charts.js` and `screens.js`, its brief `docs/plans/project-workspace-redesign/README.md`, and the picture `mockups/preview/b.png`. The page built here must be recognisably that screen: the same top bar, tabs, status strip, map, list, drawer, type, colour and spacing. What changes is where the content comes from.

**Done when:** Tuldok started with `--project-folder` on the lab folder opens to the map with the lab's 206 models in their sections and lanes, their lines, comparisons and accuracy track; a model opens its card in the drawer; the Benchmarks, Train, Data, Analysis and Overview tabs show the project's real content; every tab is captured in a headless browser in light and dark with no script error; and nothing on the page changes the project.

## 1. Decisions

- **The mockup's code is the starting point, not a picture to imitate.** Its shell, style sheet, map, charts and screens are copied into `static/` and changed only where the content's shape differs or where a part is not in this phase. The mockup read one baked object, `window.LAB`; the page builds what the screens read from the project's operations.
- **The page replaces the stand-in report page** for `/`, `/workspaces` and `/workbench` in folder mode. `static/project-folder.html`, `.js` and `.css` are removed. The report stays reachable as a link on the Overview tab.
- **Not in this phase:** Annotate (no tab); Branch from here, planned models and every other control that changes something (phase 3: such controls are not drawn, not drawn disabled); studies; the record browser and volume viewer; field slices; the Stages and Ledger layouts and the layout switch; anything the mockup generated for layout only (training curves, per-case field errors, illustrative "needs you" items, reference sizes).
- **Where the project has nothing, the screen says so in a sentence** and draws no placeholder data.
- **No build step, no framework, no external reference**, and no markup made from project text: text reaches the page through text nodes. A model's card is Markdown; it is shown by a small renderer of the page's own that makes headings, paragraphs, emphasis, lists, tables and code from it as elements.
- **Type.** Ubuntu Sans and Ubuntu Sans Mono are vendored under `static/vendor/ubuntu-sans/` with their licence, as the brief says, when the files are on the machine and allowed by that licence; otherwise the page uses the installed faces with the brief's fallbacks and the report says so.
- **Signing in** uses the existing `auth.js`. Its identity and buttons sit in the top bar's right side, styled with the page's own tokens in both themes.

## 2. What each part reads

One addition to phase 1: each model of `map` also has `description`, the first 300 characters of the recipe's description cut at a word.

| Part | Reads | Shows |
| --- | --- | --- |
| Top bar | `summary` | the project's name, the tabs Map, Data, Train, Benchmarks, Analysis, Overview, the theme control, the session |
| Status strip | `summary`, `status`, `build_requests`, `environments`, `runs` | one computed sentence of where the project stands (how many models are built, to build and cannot be rebuilt; what is running), when it was read, and "Needs you" with a count |
| Needs you | the same | a list, each item a sentence: a build request awaiting approval, files changed on disk or unsaved edits, an environment not ready, a definition whose last run ended badly, a worker that is elsewhere or stopped. No buttons in this phase |
| Map | `map` | sections from the groups that have models; a model's lane from what it was derived from; solid lines for derivations and inputs; the faint line for order; dashed arcs for the selected model's comparisons with the excerpt on hover; colour by kind of change, with the kind always named; the accuracy track from the track's values; the minimap; filters by kind and by text; the list under the map with each model's short label, title, description, kind and a bar for its track value |
| Drawer | `definition`, `note`, `recipe_results`, `runs`, `products` for the selected model | title, state, kind, group, what it was derived from and what derives from it, its comparisons, its results across benchmarks, its runs and product, then its card |
| Benchmarks | `results_overview`, `definitions` of kind benchmark and chart, `chart`, `results` | a benchmark picker; the coverage line (how many models have a result there); the benchmark's charts by their form (accuracy against time with the frontier, error along the sequence, ranking, comparison), drawn by the page from chart data so points can be hovered and focused; the all-models table, sortable; a compare set of up to three models with their values side by side |
| Train | `definitions` of kind recipe, `runs`, `build_requests`, `environments`, `progress` | models not built yet; build requests with their state; runs newest first with state, time and device, and for a running one its latest progress as a hairline and a line of text; environments with their state |
| Data | `definitions` of kind dataset, `products` | a card per dataset: title, state, whether its files were adopted, their size and count, what uses it; opening one shows its definition and its files' paths |
| Analysis | `results_overview`, `values` | a benchmark and model picker, then the per-case values as a table and a strip of one mark per case |
| Overview | `summary`, `definitions`, `environments`, `activity` | counts by kind and state, the environments, the latest activity, and a link that opens the report page |

**Refreshing.** The page reads once when opened and when the window regains focus. While a build request is queued or running it asks again every two seconds for what can change (`summary`, `runs`, `build_requests`, and `progress` of a running run), and stops when nothing runs.

**Speed.** The first screen needs `summary` and `map` only; the other tabs read when first opened; a card reads when its model is opened.

## 3. The lab folder

A model's list row shows its description. The lab's converter wrote the same conversion sentence into every earlier recipe's description. It now leads with the card's **Purpose** paragraph when the card has one, followed by the sentences it wrote before.

## 4. Checking the page

- **HTTP tests** in `tests/test_tuldok_project_http.py`: the page and each of its files are served in folder mode and nothing else is at `/`; the stand-in's paths are gone.
- **A browser check**, `tests/browser_project_workspace.cjs`, in the way of the existing `tests/browser_*.cjs` checks: starts the app on a fixture project with results (and, given `--lab-root`, on a copy of the lab folder), signs in, opens every tab in light and dark at 1440 by 900, opens a model, hovers a map node, sorts the table, and fails on any script error, failed request, sideways overflow or empty main area. It writes its screenshots where the other checks write theirs.
- The orchestrating session runs the browser check on the lab folder and looks at every screenshot against the mockup's.

## 5. Slices

| Slice | Files | Notes |
| --- | --- | --- |
| T18 shell and map | `static/project-workspace.html`, `static/project-workspace/` (style, map, the adapter, the Map and Overview screens, the drawer, the status strip and Needs you), the vendored faces, the asset rows in `app.py`, `description` in `workspace.py`, the removal of the stand-in page, the HTTP tests, the browser check for these parts | first |
| T19 other tabs | Benchmarks, Train, Data, Analysis in `static/project-workspace/`, the browser check extended to them | after T18 |
| L7 lab | `lab:scripts/build_tuldok_project.py`, its tests, the regenerated descriptions | beside T18 |
