# M2 CI observation-fixture repair

For M2 head `c22e9d02c87938514a7a1c9b3b0532158008ca0d`, the lifecycle workflow
[39842528122](https://github.com/MrScripty/Tuldok/actions/runs/39842528122)
failed at step 61, `node tests/browser_workspace_project_observation.cjs`, in job
`120047066904`. The three other workflows passed. Full Python discovery and the
new real external-project transport/cold-browser steps had passed; that does not
make the overall lifecycle result successful.

The failure was `TypeError: Cannot read properties of null (reading 'focus')`
through fixture `activate` → `holdInner` → the recipe-change loop. The fixture
counted an incoming snapshot request, then waited an arbitrary 50 ms; it could
try the next recipe button before the restored observation reached the DOM.
The exact failure was reproduced with one controlled 200 ms restoration-response
delay against unchanged c22 product controllers.

Only the observation fixture changed. It now acknowledges the exact observation
after the real Activity callback has applied it, with an incremented applied
sequence even when identity is unchanged. It neither skips assertions nor raises
timeouts. Actual Chromium 151 passed all sixteen existing checks, twenty applied
observations and zero mutations/exceptions. Syntax and whitespace checks passed.

Repaired fixture SHA256:
`5d98fff29377ba187c40c1db2cba604a37ccdc516d24bba5a3480f59093d3bbc`.
Before/after logs are retained at
`/workspace/scratch/tuldok-save-load-qa/m2ci-observation-before-20261022.log` and
`m2ci-observation-after-20261022.log` in that directory. No duplicate full-suite
campaign or CI rerun was requested; future exact-head CI must include this fix.
