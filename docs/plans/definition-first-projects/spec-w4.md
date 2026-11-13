# Implementation spec: the workspace updates in place

This continues [spec-w3.md](spec-w3.md). Section 1 of [spec-m1-m2.md](spec-m1-m2.md) (rules for implementers) applies. It changes the page only: `static/project-workspace/`, one new browser check, and the paragraph of `docs/contracts/project-folder.md` that says when the page reads. No operation, no format and no server code changes.

**Owner's report, 2026-11-12, on looking at phase 3:** "there is a full page reset when it should just be updating info on the page instead".

## 1. What was measured

The lab folder (206 models), owner signed in, nothing in the project changing. "Rebuilt" counts the elements of the main area that are new nodes afterwards.

| Tab | On return to the window | Every 15 s while idle |
| --- | --- | --- |
| Map (also with a model open, and with the editor open) | nothing | nothing |
| Data | all 356 rebuilt | nothing |
| Train | all 64 rebuilt | all 64 rebuilt |
| Benchmarks | all 2,109 rebuilt | nothing |
| Analysis | all 159 rebuilt | nothing |
| Overview | all 2,336 rebuilt | all 2,336 rebuilt |

In every rebuild the sideways scroll of the tables inside the main area went back to the start. The tab bar was rebuilt with each of them, and the status strip was rebuilt on every reading on every tab. The answers themselves were identical between readings (`summary`, `status`, `build_requests`, `environments`, `runs`, `map`, `definitions`, `products`, `activity`).

The causes, in `app.js`: returning to the window forgets every kept answer and redraws any tab but Map; the reading every 15 seconds (added at phase 3's acceptance) redraws Train and Overview whether or not anything changed; `render()` rebuilds the tab bar; `strip()` rebuilds the strip. And a drawer that is read again is emptied to "Reading…" first.

## 2. The rules

**R1. One way of reading again.** The page reads again in three cases: on its timer (every 2 seconds while a build is queued or running, every 15 otherwise), when the window regains focus, and after a control's answer. Each asks again for what the page watches: `summary`, `status`, `build_requests`, `environments` and `runs` (each with no arguments), and `map` as well on focus, after a control's answer, when a run or a request ended, and when `status` changed. Nothing kept is forgotten first. The adapter asks, and compares the text of each answer with the text of the kept one: an equal answer leaves the kept object as it is.

**R2. Nothing changed: nothing is redrawn.** When every watched answer is equal to the kept one, the page touches no element of the tab bar, the strip, the main area, the drawer or Needs you. One exception: the time in the strip's "Read at" is replaced, as text, when its minute changes.

**R3. Something changed: what is on screen is brought up to date, in place.** Every kept answer that is not watched is forgotten, so it is read again when next needed. Then:

- the strip is redrawn, and Needs you when it is open;
- the main area of the tab on screen is built off the page from fresh answers and put in place in one step;
- an open drawer is built off the page the same way and put in place in one step, except a drawer that holds the editor or the branch form, which a reading on the timer or on focus never touches (what is typed there stays; the server reports a conflict on Keep or Save, as now).

"Reading…" is shown only for a tab or a drawer subject that is not on screen yet. A control's answer always counts as a change.

**R4. What putting in place keeps.** The scroll of the main area in both directions; the scroll of every scrolling element inside the main area and inside the drawer (matched by its place in the tree: the same path of child indexes and the same tag); the drawer's own scroll; the focus and the caret, by `data-key` as now; whether Needs you is open; the selection on the map and in the lists.

**R5. The tab bar is built once.** Changing tab sets `aria-current` on the links that exist.

**R6. The map.** An unchanged `map` answer never rebuilds the tree (as now). A changed one rebuilds it in one step and keeps the scroll of the map and of the list, and the selection.

**R7. Live progress stays as it is.** While a run runs, the strip's hairline and its sentence, the open run's progress and logs, and the progress line of the run's row in Train's list are updated on each reading, as text and width set in place. Progress alone never redraws the main area.

**R8. The person's own actions redraw as now.** A sort, a filter, a tab, a selection: the tab draws again at once, by the same putting in place (R4).

## 3. Parts

**`adapter.js`.** Each kept answer is kept with its text. `again(names)` asks again for the kept answer of each named operation with no arguments (asking for the first time when none is kept) and resolves to the names whose answer differs from the kept one; for those the kept answer is replaced. When any of them is refused or does not arrive, the error is thrown and nothing kept is replaced: a refusal with code `conflict` shows the conflict panel, as now; anything else leaves the page as it is, the strip says the project was not read and why, and the page asks again on its timer. (First written as "another refusal drops the kept answer and counts as a change"; that emptied the tab on screen whenever the server could not be reached for a moment.) `forgetBut(names)` forgets every kept answer whose operation is not named. `map()` keeps returning the same shaped object while the raw answer is the same object.

**`app.js`.** `poll`, `again` and the reading part of `changed` become one routine following R1 to R3. The strip is drawn by parts that are updated only when their content differs. `render()` no longer touches the tab bar beyond R5.

**`tabs.js`.** `swap` keeps what R4 lists. `drawer(aside, id, load, build)` keeps the content on screen while it reads the same subject again, and replaces it in one step.

**`screens.js`, `actions.js`, `editor.js`.** The model's drawer, the plan view and the steps of a new model follow the same rule: read again for the subject already shown, they stay on screen until the new content is complete, then are replaced in one step with the drawer's scroll kept. The map keeps its scroll when rebuilt (R6).

No element is kept from an older drawing when its content is drawn again: what is replaced is replaced whole, so a control never acts on answers older than the ones it was drawn from.

## 4. The check

A new `tests/browser_project_workspace_still.cjs`, on the same fixture as `browser_project_workspace_actions.cjs` (owner signed in, stand-in commands, no GPU) and, with `--lab-root`, on a real folder read only. It counts added and removed nodes with a `MutationObserver` on the tab bar, the strip, the main area, the drawer and Needs you, marks the elements on screen so new ones can be told apart, and samples the page every 50 ms for "Reading…".

1. **Nothing changed.** On every tab, and with a model's drawer, a run's drawer, a build request's drawer, a dataset's drawer, the plan view and the editor open: after the window regains focus, no node is added or removed anywhere and every scroll position is what it was (main, sideways tables, the map, the list, the drawer). On Train and on Overview the same holds across one reading on the 15-second timer. Needs you open stays open and untouched.
2. **Something changed elsewhere.** With the page on Train, scrolled, and a control focused, a second session asks for a build (so it awaits approval): within one reading the strip's count and the Train list show it, "Reading…" is never shown, the scroll and the focus are what they were. With that request's drawer open, the second session approves it: the drawer shows the new state without ever showing "Reading…" and keeps its scroll.
3. **A build runs.** While the stand-in build runs, the hairline moves, the open run's drawer updates, and the run's row in Train's list shows its latest progress with no node added or removed; the main area of the Map tab gains no node until the run ends, and then the model is drawn built with the map's scroll kept.
4. **The editor is left alone.** With text typed into a field of the editor and not kept, a change elsewhere (step 2's request) does not touch the drawer: the typed text and the caret are there.
5. **A reading fails.** Cut off from the server, the page keeps what it shows and the strip says the project was not read; when the server answers again the strip says where the project stands, and nothing else was touched.
6. The existing browser checks pass unchanged in what they assert.

With `--lab-root` only step 1 runs, and nothing is asked of the project that changes it.

## 5. Out of scope

Patching single values inside a tab's content (only the nodes that differ): a tab whose answers changed is replaced whole, in one step. Server-side change tokens. Any change of what a tab shows.

## As built

What differs from the text above, and what was found while building it.

- **Needs you is redrawn only when what it lists differs.** R3 says it is redrawn whenever something changed and it is open; it is drawn again when its items (kind, key and sentence of each) or the signed-in identity differ, and when it is opened. A reading that changed something else leaves it untouched.
- **The map is rebuilt in the page, not off it.** R6's rebuild runs synchronously in the main area (the lane map needs its container on the page to measure itself), so it is one step for the viewer; the scroll of the map and of the list is put back when the filters are the same, and a new selection or a change of filter or zoom still scrolls to the selected model as before. An unchanged tree draws only a selection that differs (it used to redraw the comparison and input arcs on every render).
- **The model's drawer, read again, waits for every block** (Results, Runs and product, Uses, Card and the steps of a new model) before it is put in place; `steps()` in `editor.js` now returns its promise and fills its box whether or not it is on the page yet. The Benchmarks tab passes its Compare buttons to `inspectorModel` so that a drawer put in place later carries them.
- **The report** (Overview → Open the report) keeps the frame on screen while it reads again and puts the new one in its place; "Reading…" only the first time.
- **After a control's answer** `press()` (`actions.js`) forgets what is not watched before its `done` step, instead of every kept answer, so that the watched answers can be compared by the reading that follows. A view `done` opens (a new build request, say) is drawn from fresh answers for its own subject; the tab's lists may show the watched answers of a moment earlier until that reading, which follows at once, puts them in place.
- **A refusal reads again as on focus** (the watched answers and `map`, no forced change); it used to recompute from the kept answers without asking.
- **When the open run ends** its drawer is no longer emptied: the reading that follows (as after a control's answer) draws it again in place.
- **One reading at a time.** A timer, focus or control reading that arrives while one runs waits for it; of several waiting, the strongest cause is kept (control over focus over timer).
- **Two things are set in place on every reading though nothing changed** (found in review: as first built they went stale until a watched answer changed): the progress line of a running run's row in Train's list (`S.progress` in `tabs.js`: the hairline's width and the line's text; the row's first progress replaces its one line) and the "Read at" time on the Overview tab. `app.js` reads the latest progress of every running run on each reading.
- **A reading that fails changes nothing** (found in review). `again()` asks for all the named answers before it replaces any, and throws when one is refused or does not arrive. The page then keeps everything on screen, the strip says "Not read" with the reason and the time of the last reading that succeeded, and the timer asks again. When the failed reading followed a control's answer, the next one that succeeds counts as a change.
- **Needs you's key** also holds the references behind an item, so its controls are never older than its sentence.
- **`docs/contracts/project-folder.md` had no paragraph on when the page reads;** two sentences were added to the paragraph that describes the page.
- **The controls check waits for the page's requests.** `tests/browser_project_workspace_actions.cjs` asserted the editor's header the moment a control stopped being busy; the drawer is now drawn again by the reading that follows, a few milliseconds later, and the check failed twice in a row on a busy machine. Its `settled()` now also waits until the page has no call of the project in flight. No assertion changed.
- **The check** (`tests/browser_project_workspace_still.cjs`) waits for a reading by the page's own requests (the watched operations answered after a moment, then nothing asked for 700 ms), and changes the viewport height for two sub-steps so that the request's drawer, the map and the list scroll on the small fixture. It counts attribute and text changes as well as nodes; in step 1 every one is zero except the "Read at" text. Once, before the viewport for step 3 was made shorter, the list's scroll was found clamped by the browser (43 to 9 px) before the map was rebuilt: the list's scroll range shrank when the run ended, so the page had no larger value to put back. The cause of the layout change was not found (the strip's height was the same before and after in the run that measured it).
