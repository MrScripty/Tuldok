# Access browser navigation and shutdown qualification

The local repair descends from PR112 at
`0dedbc953902ac89389dca0693006aaa02a0a87c` on
`fix/access-browser-ci-qualification-20261020`. Root owns subsequent serial
integration. This branch is unpublished and retained for review; no remote PR,
workflow, branch or hosting state changed.

The implementation changes three test files only. Both the initial workbench
navigation and scoped-agent reload capture the previous main frame/loader and
wait for a changed main loader with its matching load event before reading DOM.
The helper reuses the existing CDP session and load tracker. Request, connection
and document-load waits are bounded; failure context contains phase, method and
bounded frame/loader identities without command parameters. All 14 original
assertions remain, with one added assertion selecting the explicitly launched
blank page. No authentication or product behavior changes.

Shutdown now awaits the existing supplied-child helper before bounded removal of
the exact test profile. Primary access failures and secondary cleanup failures
retain separate labels and a nonzero outcome. Main-handle termination does not
establish an unconditional Chromium-descendant shutdown guarantee.

## Evidence

- [Controlled regression](../../../../../tests/test_browser_access_navigation.cjs)
  reproduces the old navigation/reload acknowledgement ordering with the exact
  `-32000` error. The corrected sequence issues no DOM read before the changed
  main loader's load; old-loader, subframe and DOMContentLoaded events cannot
  release the gate. Target closure and request/load timeout cases remain failures.
  This is a controlled protocol reproduction, not the original hosted trace.
- Three syntax checks, the new regression, the existing page-load regression,
  owned-child delayed-write/ignored-TERM regression and diff check passed.
- The unchanged default command `node tests/browser_access.cjs` passed against
  actual existing PostgreSQL17.6, Python3.12.14, Node24.19.0 and Chromium151 in
  8.605350 seconds. It includes the new regression before its real browser journey.
  [Raw log](actual-access.log), [actual receipt](receipt.json), [runner](runner-receipt.json)
  and desktop/narrow screenshots retain the result.
- The initial owner login still uses an actual one-time CLI code and interactive
  browser form, not a preinstalled fixture cookie. Anonymous denials, HttpOnly/code
  clearing, retained drafts, no mutation replay, deliberate commit and final
  scoped-agent review denial all pass. The final scoped-agent switch installs its
  separately issued real credential as in the original test.
- [Cleanup](post-run-cleanup.json) records the exact preregistered schema queried
  absent after disposal, zero workspace Runs, terminal supplied app/browser
  handles, absent exact profile and no matching task process at observation.
  Only the disposable fixture was removed; no service or package was installed
  or reconfigured. Reviewer inspected these receipts, not a second PG/browser run.
- [Independent review](independent-review.json) clears source, focused checks and
  actual evidence. It rechecks all three tested source hashes. The actual receipt
  records precommit HEAD0ded with dirty source; file hashes bind the tested repair
  bytes and must match the eventual local commit. It does not claim 0ded already
  contained the repair.

## Original failure and remaining gates

Original run39370107550/job118455819881 remains failed at access step41.
Its [excerpt](original-failure-excerpt.log), full decoded-log SHA and source
identity are retained in [qualification](qualification.json). The log provides
no failing command/phase trace, so exact navigation versus target closure/crash
remains unproven. Cleanup ENOTEMPTY followed the primary error and is separate.
The artifact ZIP was proxy403 blocked and its contents remain uninspected.

The running sibling CI was untouched. No cancellation, rerun, source publication,
merge or branch/worktree cleanup occurred. This local access qualification is
not a passing full repaired-head lifecycle; fresh hosted gates and independent
integration review remain necessary when publication is authorized. PUB-1 original
diagnostic evidence and SCI-1 owned criterion/compatible real lab pair remain
missing. No training, scientific, CUDA or model-quality acceptance is inferred.
