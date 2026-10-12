# Audio browser gate: embedded toolbar readiness

The CI-mode headless audio gate clicked the embedded toolbar before its script
had attached it. `workbench.js` can report **Collection ready** while the later
`workspaces-data.js` is still loading. The catalog notice alone therefore did
not establish readiness for the import dialog.

The repair changes only the browser test's `tools()` helper. Before clicking it
waits for the visible catalog, complete embedded document, connected and enabled
rendered toolbar button, connected dialog, and existing public workspace bridge.
The existing polling interval, deadline, dialog-open assertion, and all twelve
workflow checks remain unchanged. No application runtime or capability changed.

Base: `418d6cbda8bab67ecb30c925da815e202cc8fc4f`.
Branch: `fix/audio-browser-embed-readiness-20261012`.
Verified test-file SHA-256:
`b1ce2dc7031124a70ea87bd5d2f78be54c973db9d9fed5d8da3d4d9b98bb17bf`.

## Verification on 2026-10-12

- A temporary CDP discriminator held the real `workspaces-data.js` response until
  the core notice read **Collection ready**, asserting that the toolbar and dialog
  were both absent. The original test from the base commit then failed with
  `Cannot read properties of null (reading 'click')`, reproducing the reported
  headless failure deterministically.
- With the repaired test, the same discriminator observed the readiness predicate
  return false before releasing the held script. All twelve original checks then
  passed. No arbitrary delay or deadline extension was added.
- The unmodified repaired test also passed all twelve checks in normal headless
  Chromium with the least-privilege PostgreSQL app role and the local-only network
  preload. `node --check tests/browser_workspace_audio.cjs` and `git diff --check`
  passed.
- The independent integration reviewer inspected the exact test hash, complete
  diff, discriminator and both outcomes. The candidate was accepted with no
  runtime drift or weakened assertions. Root retains serial integration and CI
  ownership; this local result does not claim a hosted CI pass.

Retained local evidence in `/workspace/Tuldok-audio-readiness-20261012`:

| Evidence | Location |
| --- | --- |
| Delayed repaired receipt, 12 passed checks | `build/qa/workspace-audio/run-vj8Pww/receipt.json` |
| Normal headless receipt, 12 passed checks | `build/qa/workspace-audio/run-tdptyL/receipt.json` |
| Deterministic discriminator | `/tmp/tuldok-audio-readiness-proof.cjs` |
| Original failure log | `/tmp/tuldok-audio-readiness-baseline.log` |
| Delayed repaired log | `/tmp/tuldok-audio-readiness-repaired-delayed.log` |
| Normal headless log | `/tmp/tuldok-audio-readiness-headless.log` |

Both candidate receipts correctly record the base commit and `dirty=true`; the
exact verified test bytes are identified above. These are headless twelve-check
runs, not a new native-zoom qualification or replacement for the earlier audio
feature screenshots.

Normal headless command in the qualification environment:

```sh
PATH=/tmp/tuldok-app-venv/bin:$PATH \
TULDOK_DATABASE_URL='host=/tmp/tuldok-pg/socket port=5432 dbname=tuldok user=tuldok passfile=/tmp/tuldok-pg/app.pgpass' \
BROWSER=/usr/bin/chromium LD_PRELOAD=/tmp/tuldok-offline-loopback.so \
node tests/browser_workspace_audio.cjs
```
