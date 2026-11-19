# Plan: the Map workspace, for real

**Status: approved by the owner on 2026-11-12 ("the plan looks good"), with the three recommended decisions.**

## Summary

The interface the owner chose on 3 November, the Map layout of [the workspace redesign](../project-workspace-redesign/README.md), exists only as mockups that run from disk with the lab's content baked into a data file. The Tuldok app has never shown it. What the app shows for a project in the new format is one report page, which was a stand-in.

This plan makes the Map layout the app's interface for a project folder. The mockup's screens are kept as they were reviewed; what changes is where their content comes from: the operations of the new core, live, in place of the baked data file.

**The test:** start Tuldok on the lab folder and see the screen of the mockup, with the lab's 206 models on the map, their real results on the Benchmarks tab, and runs and build requests on the Train tab; then approve a build from the screen and watch it run.

## What the mockup has, and where each part comes from

| Tab | In the mockup | From the new core | In this plan |
| --- | --- | --- | --- |
| Top bar and status strip | project name, tabs, theme, "Needs you" | name and counts; build requests awaiting approval, files changed on disk, environments not ready, failed runs | Yes. The status sentence is computed, with an optional authored line |
| Map | models left to right in sections and lanes, accuracy track, minimap, list, drawer with the card | recipes ordered by training date; result summaries for the track; the card from `notes/fits/`; runs and products | Yes. Needs groups, the kind of change, and comparisons to become authored fields: see below |
| Branch from here | a planned model drawn on the map, with its training setup | a new recipe written from its parent as an unsaved edit, then a build request | Yes, second phase |
| Train | planned models, every training run, studies | recipes not built, runs with live progress, build requests, environments | Yes, without studies: the new format has none |
| Benchmarks | coverage line, accuracy against time with the frontier, error along the sequence, compare set, all-fits table | result summaries and chart data | Yes |
| Data | dataset cards; records as thumbnails; a volume viewer | dataset definitions, their state and product size | Cards only. The record browser and the volume viewer need Tuldok to read inside products; that is a later plan |
| Annotate | records, labels, review | nothing | No. Annotation data is not in the new format; it has its own plan |
| Analysis | field slices per case; plans with their documents | per-case values | Per-case values only. Field slices come with the volume viewer |
| Overview | where the project stands | summary, definitions by kind and state, activity | Yes |

## What has to be added to the format

The map needs three things that today live in a lab notes file Tuldok does not read (`notes/model-groups-and-comparisons.json`) or only in the mockup:

1. **Groups.** Which section and lane a model belongs to. Proposed: `group` on a recipe, and a `groups` list in `tuldok.json` with each group's title, parent and order.
2. **Kind of change.** The colour of a branch: training policy, architecture, refinement or component. Proposed: `kind` on a group, authored. For the lab I would carry the mockup's rule over as the starting values, for the owner to correct. *Corrected when phase 1 was specified:* in the mockup the kind belongs to each model, not to its group (one group holds 31 architecture and 20 refinement models), so the field is `change` on a recipe, and the lab's starting values are the mockup's own, model by model.
3. **Comparisons.** The dashed arcs. Proposed: `compared_with` on a recipe, a list of the other recipe and the note's explanation.

Ancestry lines are the graph's existing edges: a recipe that takes another recipe's weights as an input. The mockup inferred three branch points from card text; the real lines will be only what the definitions record, so some may be missing until those inputs are written down.

The accuracy track and the row bars read one chart definition of the `progression` form, named in `tuldok.json`.

The lab's folder is changed once more by its converter to move groups and comparisons into these fields, since nobody has edited the folder by hand yet.

## What has to be added to Tuldok

- **Operations:** `map` (every model with its group, kind, date, state and track value, the edges, comparisons and groups, in one answer), `note` (one file under `notes/`, bounded), and results for one recipe across benchmarks.
- **The page:** the mockup's `b-map.html`, `screens.js`, `tree.js`, `charts.js` and `base.css` (about 1,900 lines) become the app's page for a project folder, reading from the operations. No build step, no framework, no external reference, as now. Ubuntu Sans is vendored under `static/` as the brief says. The Stages and Ledger variants are not carried over.
- **Live state:** the page asks again only while something is running, about once a second, and shows progress as a hairline.

## Phases

| # | Phase | Size | Done when |
| --- | --- | --- | --- |
| 1 | Format fields for groups, kinds and comparisons; the `map`, `note` and per-recipe results operations; the lab folder carries them | Small | The lab's `map` answer has 206 models in their sections with kinds, the 26 comparisons and a track value where a result exists |
| 2 | The page, read-only: top bar, status strip, Map with list and drawer, Benchmarks, Train, Data cards, Overview | Large | The lab opens to the map of the mockup with real content; each tab is checked in a headless browser in light and dark, and the owner looks at it |
| 3 | Acting from the page: approve, decline and cancel build requests; plan and request a build; branch from here; edit and save a definition; resolve a conflict; the "Needs you" list | Medium | On the tiny example, a model is branched, its build requested and approved from the page, and its progress watched there |

Each phase is specified, built by Opus 5.5 agents at medium effort and reviewed as the milestones were. Phase 3's check runs the same tiny training as before, a few seconds of GPU.

## Out of scope

- Annotation, the record browser, the volume viewer and field slices.
- Studies, trials and candidate selection.
- Any change to catalog mode or to the old project page. The old project mode is not deleted before phase 3 is accepted, whatever the capability check says.

## Decisions needed

1. **Scope.** Phases 1 to 3 as above, leaving out Annotate and the viewers. Recommended.
2. **Where groups, kinds and comparisons are authored.** In the definitions and `tuldok.json`, as proposed. Recommended, because then they travel with the project and Tuldok needs no lab-specific file.
3. **The mockup folder.** It is not in Git; it exists only on this disk. Its data file holds the lab's model names and notes. Commit all of it to the Tuldok repository, commit it without the data file, or leave it local. Recommended: commit it without the data file, and keep the data file beside it, ignored.

## Risks

- **The real lineage is thinner than the mockup's.** Only recorded inputs draw a line. The map will still show sections, lanes and order; branch lines appear as inputs are recorded.
- **206 models with their cards.** The `map` answer must stay one query and well under a megabyte; cards load when a model is opened.
- **The mockup's training curves and field errors were generated for layout.** Where the real project has no such data, the screen says so and draws nothing.
