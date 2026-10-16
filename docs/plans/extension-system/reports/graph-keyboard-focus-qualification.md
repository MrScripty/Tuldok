# Saved-graph keyboard focus qualification

Selecting an external saved graph disabled and replaced the focused native
select, leaving focus on the page body. A keyboard user could not continue to
the next graph. The action now remembers the initiating control before disabling
it and restores it after rendering only when the view and navigation generation
are unchanged and focus remains on the body. Moving focus to another control or
navigating away prevents restoration. External synchronous rendering also reuses
the existing focus-preservation helper.

Independent real Chromium151 qualification uses a disposable neutral Project,
three saved external graphs and zero recipe Runs. The exact same harness
`8ae8c453068c49384898a58f65e1baa5df2a235621f5e37d5150f7bfc7d93cc5`
focuses once, sends physical Home/ArrowDown/ArrowDown and waits for each selected
value and enabled control. On the old application all three observations have
BODY focus and remain on the first graph. On the fixed application all three
graphs are reached with SELECT focus. Held GET responses additionally prove
that separately moved focus and navigation to Runs are preserved.

- [Old-source actual receipt](examples/graph-keyboard-focus/old.json), application
  SHA `9d7f59f928298d9fd1e851f7823b265eccee3c6a499de8a61f71d838d1a7eb77`.
- [Fixed-source actual receipt](examples/graph-keyboard-focus/fixed.json), application
  SHA `7d968878edd253bb7e1409693edce03b66b1787f64cfe83f2b2d8ad380b185e6`.

The field/retention browser harness now requires one initial focus and preserved
focus after every settled native selection; it cannot repair focus per key.
Node syntax and whitespace checks pass. This is a late UI-only correction after
the independently frozen A/B source, package and original native qualification.
Their149-file application freeze and numerical/source evidence retain their
original exact host. No numerical producer, custody, material, SDK or source
package changes; final restored native inspection uses this corrected UI.
