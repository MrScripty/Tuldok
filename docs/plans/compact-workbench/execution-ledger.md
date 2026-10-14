# Reconciliation ledger

- 2026-10-14: inspected original PR33 and modern main/P7 context. Root admitted
  main `f2751c3224ed0280ba285262698d15144a8fed9f`; created isolated descendant
  of original owner `581fa5c`, preserving its four commits/captures. Current
  merge requires resolving only app registration and workbench markup. Chosen
  standalone DOM adapter retains current markup and embedded owner.
- 2026-10-14: reconciled existing-main HTML/includes and static map; standalone
  adapter and scoped CSS retain modern controls and embedded production owner.
  Initial browser control-preservation oracle caught an attachment-order error;
  corrected before acceptance. Independent review caught an embedded stale
  marker; scoped it to the standalone hook and added controller/actual-browser
  regressions. Corrected historical/current documentation claims.
- 2026-10-14: 35 actual Chromium gates,15 Python tests,11 controller suites,
  source syntax/whitespace and adopted plan-contract validation passed. Missing
  instruction-consumer packages resolved in an isolated environment; native
  spatial readers selected via the supported explicit interpreter variable.
  No skips, weakened assertions, pretrained downloads or training. Source-bound
  receipts and two visually inspected selected captures are in `reports/`.
