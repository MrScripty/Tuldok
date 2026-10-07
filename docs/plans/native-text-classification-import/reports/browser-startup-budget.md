# Bounded workbench-browser debugger startup allowance

## Observed failure and authorization

Failed exact-head push [37555317371/job112580086733](https://github.com/MrScripty/Tuldok/actions/runs/37555317371/job/112580086733) checks out row-repair head `7d20e5aa3957f385206fa4b7b45c33195f80df2c`. Its workbench-browser step began 01:06:36.202 UTC; the existing ~15-second wait failed at 01:06:51.540 with PID 2911 alive, no exit code/signal/spawn error and no DevToolsActivePort file. Logs show DevTools listening at 01:06:56.713, ~20.51 seconds after step start, before any navigation. No fatal Chrome error was recorded. D-Bus diagnostics also occur in successful runs; the underlying delayed-startup cause is unproven. Preserve this failed run and earlier failures without rerun.

Parent explicitly authorized a maximum 60-second TEST-STARTUP readiness budget for this evidence-supported boundary, replacing the earlier no-deadline-change restriction only here. This is infrastructure allowance, not a product/UI deadline relaxation or a claim of healthy browser behavior from port-file readiness.

## Narrow owner and unchanged behavior

`tests/browser_startup.cjs` owns only waiting for the selected child's debugger port file. Its maximum/default budget is 60,000ms. Child error/exit events reject promptly, and already-dead children cannot pass through stale files. Read failures propagate. Every success/failure removes its listeners and cancels its polling/deadline timers. It does not launch or kill children, retry browsers, adjust flags/network/environment, navigate or evaluate product state.

Only `tests/browser_workbench.cjs` uses it. The existing caller still owns launch, bounded stdout/stderr tails, failure diagnostics and child/profile cleanup; diagnostics now include the startup budget. The generic 150 x 100ms UI wait, all eight product assertions, the full post-startup CDP/browser workflow and cleanup remain byte-identical to 7d20e5a. Row-repair source and all fourteen native HTTP regressions are byte-identical to 7d20e5a. No application source changes and no broader browser-suite refactor.

## Qualification

Controlled real Node children demonstrate readiness delayed 20,510ms under the actual 60-second default (observed 20,570ms in the workflow run), a live child exhausting a scaled 250ms budget, prompt rejection after observed exit/spawn error, stale-file rejection and listener cleanup. These checks prove policy only. The final controlled-launcher test revision also passed separately (20,568ms readiness); it measures rejection relative to observed child events so cold child bootstrap time is not confused with failure-detection latency.

All 28 local lifecycle gates passed: 194 Python tests, five workflow JS syntax checks, eight controller/page-load/startup gates and fourteen ACTUAL Chromium suites. New/helper/caller syntax checks also passed. The workbench actual lifecycle and frozen download assertions ran successfully after debugger readiness; the full native import -> human review -> saved selection -> preview -> frozen ZIP/reload/navigation workflow also passed. Unrelated generated screenshots were restored/excluded. Fresh exact-head and PR-synthetic hosted CI must qualify the published successor; its results/identities are recorded in PR15, without treating late DevTools alone as healthy Chrome.

## Tested startup source SHA-256

- `tests/browser_startup.cjs`: `1fc015acd4e3ae78dc0d866adafca6589ebc5d28891ae48ea965c92126f547ae`
- `tests/test_browser_startup.cjs`: `7107db4e44f3211b1da8804574f55e02a77b6666d96a32830249fdee17ae82e4`
- `tests/browser_workbench.cjs`: `38157f073988581ac092eba3b0de430699efacd95269aa25f2ad797656a69192`
