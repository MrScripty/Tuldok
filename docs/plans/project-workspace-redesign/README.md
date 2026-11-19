# Project workspace redesign

Design brief and local mockups for the screen you see when you open a project.
Today that is `/project-files`: about twenty form panels stacked on one page
(project file, candidate preparation, runtime capture, save-as, scripts and
notes, fork origins, text records, progression, measurements, data and history,
authoring, model and study creation, scientific import, local execution, native
execution, study execution, producers). Every control is present; nothing tells
you where the project stands or how its models came to be.

The mockups in [`mockups/`](mockups/index.html) show the same project three
ways. They run from disk or from a local `http.server`, use no network, no build
step and no remote fonts, and read real content from the Rheon Surrogate Lab
portfolio (205 recorded fits, 26 authored comparisons, 9 data references, 25
evidence notes). They are design mockups, not Tuldok code: see
[What is mock](#what-is-mock).

## Run

```sh
cd docs/plans/project-workspace-redesign/mockups
python3 -m http.server 8099 --bind 127.0.0.1
```

Open http://127.0.0.1:8099/ or open `mockups/index.html` directly. Add
`?theme=dark` or `?theme=light` to any page to force a theme; the toggle in the
top bar also cycles system, light and dark.

## Who it is for and what it must do

One person, running long careful experiments on their own machine, opening the
same project many times a day. The screen has three jobs, in this order:

1. Say where the project stands and what needs the person, in one glance.
2. Show how the models came to be: the main line, where it branched, why, and
   how the measured error moved. Let the person reach any fit in a few seconds.
3. Carry the pipeline end to end: data, annotation, model definition, training,
   benchmarks, analysis, for text, audio, 3D and image projects alike.

## Calm Technology, applied

The Calm Tech Institute lists eight principles and certifies against six
criteria (attention, periphery, durability, light, sound, materials). The
mockups turn them into rules:

| Principle | Rule in these mockups |
| --- | --- |
| Require the smallest amount of attention | Status is one sentence from the producer, not a row of tiles. Each stage carries a one-line state so the navigation is also the summary. |
| Inform and create calm | Only three kinds of thing interrupt: approval waiting, source changed, file missing. They are a list with a button each, never a modal or a toast. |
| Make use of the periphery | Variant A keeps stage states in the rail; B keeps the status strip above the map; C keeps counts in the table of contents. Live progress would be a hairline, not a spinner. |
| Amplify the best of technology and of people | The machine sorts, filters, lays out and measures. Judgement stays visible as text: purpose, outcome, lesson, decision, review state. |
| Communicate without speaking | State is a glyph and a word in a muted colour. No sound, no pulsing, no motion that the person did not start. |
| Still work when it fails | Missing, unverified, unavailable and unknown each have a label and a next step. A missing file dims one row; the rest of the project keeps working. The pages work offline. |
| The minimum technology needed | Plain HTML, CSS and SVG, matching Tuldok's no-build-step rule and its `'self'` content security policy. No framework, no chart library. |
| Respect social norms | Keeps Tuldok's vocabulary (Data, Pipeline, Runs, Study, Trial, Run, Candidate) and its refusal to claim more than was measured. |

## Design system

**Colour.** Cool, low-chroma surfaces so the data marks are the only saturated
thing on screen. Status colours always sit beside a word.

| Role | Light | Dark |
| --- | --- | --- |
| Page / surface / hairline | `#f3f5f7` / `#ffffff` / `#dfe4ea` | `#0f1317` / `#171c22` / `#2a323c` |
| Ink / secondary / muted | `#1b2330` / `#596679` / `#8a94a3` | `#e6eaf0` / `#aab3c0` / `#7c8694` |
| Accent (selection, one primary action per view) | `#2c5fb8` | `#6a9ae8` |
| Good / attention / serious | `#237c60` / `#b4700e` / `#b7452b` | `#4fb68f` / `#d9a04a` / `#e07a5f` |
| Branch kind: training policy / architecture / refinement | `#178f74` / `#2e6fcf` / `#d2652f` | `#22a07f` / `#4f8ae0` / `#d96f3c` |
| Branch kind: component | neutral `#8a94a3` | neutral `#7c8694` |

The three branch hues were checked with the data-visualisation palette
validator on both surfaces, all pairs: worst colour-vision-deficiency
separation ΔE 8.9 light / 9.7 dark (target ≥ 8), worst normal-vision ΔE 19.1 /
18.2 (floor 15), all ≥ 3:1 contrast. A fourth hue did not pass, so the fourth
kind is neutral grey and every kind is always named in text.

**Type.** Ubuntu Sans for everything, Ubuntu Sans Mono for identifiers, hashes
and paths. It is the face of the platform Tuldok supports, it is already
installed there, and it reads well at 13px in dense lists. The implementation
vendors it under `static/` so the policy stays `'self'`. Scale: 12.5 / 13 /
14 / 16 / 17 / 20 px; weights 400 / 500 / 600; prose at most 66 characters a
line; tabular figures only in columns and axes.

**Layout.** Left-aligned, hairlines instead of boxes, no shadows, one 4px
radius. Sections are a heading plus a quiet summary line. Lists are the
primitive: references, studies, fits and evidence all use the same row.
Forms do not stack on the page; the action lives on the thing it acts on and
opens in the inspector.

**Copy.** Sentence case, plain verbs, the same word for an action everywhere.
No explanatory subtext: a heading carries a count or a state, never a sentence
about itself. The chrome holds no project words; metric names, populations,
group names, decisions and evidence come from the project's own data, so the
same screens serve a fluid lab, an image classifier or an audio corpus.

## The three variants

| | A · Stages | B · Map | C · Ledger |
| --- | --- | --- | --- |
| Home | Overview: status, needs you, stages, recent studies | The lineage map with the status strip above it | The whole project as one document |
| Navigation | Left rail in pipeline order with a state line per stage | Tabs; the map is first | Sticky table of contents with counts |
| Inspector | Fixed right column | Drawer over the map, Escape closes | Opens beside the selected row, inside the section |
| Lineage | Vertical list with lanes, sticky section headers | Horizontal timeline, branch lanes, metric track, minimap | Vertical list |
| Best for | Stage-by-stage work; projects not mainly about model history | Model-first thinking; long branching histories | Reading end to end; smallest implementation |
| Risk | Rail plus inspector leaves less width for the list on small screens | A long timeline needs the minimap; new users may not see the other stages first | Long page again if sections are not disciplined |

## Screens (as of the fourth review round)

Jeremy chose B, Map, on 3 Nov 2026. A and C stay reachable from the Layout
switch; the parts are shared, so every screen below appears in all three.

- **Map.** Lanes: checkpoints left to right, each branch family in its own
  lane labelled where it starts. Height never encodes a number, so edges do not
  overlap; an optional Accuracy track beneath the lanes draws the error curve
  on the same timeline without branch edges. Hover or focus a node for its name
  and numbers. Dashed arcs are the portfolio's authored comparisons for the
  selected fit; hovering one shows the note's excerpt. Selecting a fit updates
  in place: the target highlights at once, a short run of highlights steps
  from the previous selection to the new one in both the list and the map (at
  most about half a second, skipped under reduced motion), the views scroll
  smoothly and the drawer slides in.
- **Branching.** Select a fit and choose Branch from here. A planned model is
  appended to the graph right after its parent, in the parent's lane, drawn
  hollow and dashed. Its node holds the training setup: name, kind of change,
  recipe (short list), data, runtime, updates and learning rate, attempts and
  wall budget, target metric and threshold, intended change, then Prepare
  trial. The parent is picked on the graph, never from a list of models.
- **Data.** Datasets as preview cards with kind, record count, grid, size and a
  hash glyph; paths open the folder. Opening a dataset shows its records as
  thumbnails (paged) with a volume viewer: an isometric stack of slices, a
  single slice, field and slice controls, grid, spacing and timestep. Import,
  Generate and Release open panels with their inputs. Annotate goes to the
  annotation stage.
- **Annotate.** Dataset and task pickers, a filter (all, unreviewed, accepted,
  needs work), progress, records with review badges, the same viewer, and a
  form for the current record: class labels or tags with number-key
  shortcuts, Accept / Needs work / Reject, notes, Save and next, Skip, and the
  saved history. Arrow keys step through records; Enter saves.
- **Train.** Planned models first; then every training run (one per fit, in
  checkpoint order, with updates, learning rate, seed, loss, device and the
  study it belonged to when known); then the seven budgeted studies. A run's
  detail shows its recorded training setup and Branch from here. A study's
  detail shows baseline, recipe, runtime, data, budget, intended change, the
  runs in it, steps and documents.
- **Benchmarks.** A coverage line says how many fits have accuracy and time,
  accuracy only, time only, or no retained benchmark, so the smaller plotted
  count is explained rather than implied. Population switch, kind filter,
  metric, frontier-only, benchmarked-only and search. Accuracy against time
  with the Pareto frontier; error along the checkpoint sequence; a compare set
  of up to three fits with a delta table and training curves; a sortable
  all-fits table with a Benchmark column; study results with reference versus
  candidate and the change. A fit without a comparable benchmark offers Run
  benchmark through the evaluation recipe.
- **Analysis.** Field comparison per case: native, predicted and signed error
  slices for a chosen fit, case and slice, with the per-case error strip. The
  slice slider redraws while dragging. Then one row per plan with its outcome
  and its documents as three small links.

Shareable states for review: `?branch=<fit id>` seeds a prepared planned model
from that fit; `?cmp=<id>,<id>` seeds the compare set; `?theme=dark` forces
the theme.

## The lineage view

Both renderings read one graph built from the portfolio note:

- Order is checkpoint order (C03 to C130), then the complete generators, then
  the components. Authored groups become sticky sections or labelled bands.
- A solid line is a derivation. In the mockup it is read from the card text
  ("C53 fine-tune", "initialized from exact C53 values"), which finds three
  branch points: 15 fits from C53, 3 from C44, 4 from C37. In Tuldok this edge
  comes from the Trial lineage sidecar, and historical fits without a sidecar
  stay "no recorded ancestry", as the inspector says.
- The faint line is checkpoint order only and makes no ancestry claim.
- A dashed line is an authored comparison; it appears only for the selected
  fit so the graph stays quiet.
- Colour is the kind of change on a branch (training policy, architecture,
  refinement, component). The mapping from authored group to kind is a mockup
  rule; in Tuldok the kind would be an authored field on the portfolio entry.
- Each row carries a small bar for worst pressure relative L2 on a log scale,
  so a branch's progress is visible without opening anything.

## Benchmarks

Accuracy against time is a scatter of worst pressure (or equation) relative L2
on a log axis against median GPU milliseconds per call, with the Pareto
frontier drawn through the fits no other fit beats on both. Hover and keyboard
focus read every point; a table view holds every value. The second chart is
the same error along the checkpoint sequence. Both say what population they
plot. Generators are kept off these charts because their task and population
differ, exactly as the portfolio note says.

## What is mock

- Studies, the "needs you" items, reference sizes and the missing file are
  illustrative; the manifest, evidence list, fits, metrics, aliases, groups and
  comparisons are real.
- Evidence previews show a placeholder instead of the bounded text.
- Derivation edges are inferred from card text for the mockup only.
- Training curves and per-case field errors are generated for the layout from
  each fit's recorded update count, final loss and worst error; the field
  slices are synthetic. The real screens read retained measurements and the
  paired-frame dataset.
- Recipes, runtimes, trial rows, annotation tasks and the twelve seeded
  annotations are hand-authored. Record thumbnails and volumes are synthetic.
- Buttons do not call anything. "Branch from this fit", "Approve reviewed
  Trial" and "Import fields" mark where the existing explicit operations would
  be invoked; none of them would start a Run.

## After the review

Each page has a Layout switch in its top bar that opens the same screen in the
other two proposals.

1. Pick a variant, or a combination (the parts are shared, so A's rail with B's
   map is a small change).
2. Refine on the chosen one: naming, density, what the first screen shows for
   a dataset project rather than a lab project.
3. Write the implementation plan against the existing owners: project files,
   model portfolio, experiment lineage, retained measurements and live activity
   already expose what these screens need; the lineage kind and the derived
   parent are the only new fields. Keep the `'self'` policy, vendor the font,
   and extend the browser gate with the desktop and mobile, light and dark
   captures it already takes.

## Sources

- Calm Tech Institute, principles: https://www.calmtech.institute/calm-tech-principles
- Calm Tech Institute, certification criteria: https://www.calmtech.institute/calm-tech-certification
- Amber Case, "We are not bad at technology, technology is bad at us" (the eight principles with examples): https://oreilly.com/content/principles-calm-technology-we-are-not-bad-at-technology-technology-is-bad-at-us
- Portfolio contract: [`docs/contracts/project-model-portfolio.md`](../../contracts/project-model-portfolio.md); lineage contract: [`docs/contracts/experiment-lineage.md`](../../contracts/experiment-lineage.md); current workspace: [`docs/contracts/project-workspace.md`](../../contracts/project-workspace.md)
