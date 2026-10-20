# Caption browser dialog CI repair

The cancelled obsolete PR105 duplicate run39349523584/job118390149863 reported
`No dialog is showing` at02:06:23, with no runtime exceptions. It produced no
completed page diagnostics before manual cancellation at03:22:40. The original
[observation](original-task-observation.json) and [failure excerpt](original-failure-excerpt.log)
retain its cancelled outcome and exact full-log/raw-response identities. A
same-head primary passed. This is a nondeterministic harness failure, with no
product-failure claim. A late modal blocking the old diagnostic evaluation is a
source-supported hypothesis; the hosted log contains no modal-event trace.

The repair starts from published PR111 head
`0ba4db01f04a77c262eb4b397f88849e9688b5ab` on
`fix/captions-dialog-ci-qualification-20261020`. Its implementation write set is
`tests/browser_captions.cjs`, `tests/browser_cdp_session.cjs` and
`tests/test_browser_cdp_session.cjs`. Product code and all original assertions
are unchanged. The existing caption CI entrypoint awaits the focused regression
before launching the browser, so no workflow change is needed.

Each modal expectation is armed before the triggering click. The helper waits
for the fresh exact confirm type/message, handles the selected decision once,
then awaits the original click command. Cancel retains the unsaved caption;
accept restores the saved caption; discard after a keyboard edit restores human
review. Unexpected and absent dialogs fail. No autoaccept or ignored protocol
error replaces these witnesses.

CDP requests expire, timed-out replies are ignored, timers clear on terminal
outcomes, and socket closure/error drains pending requests. Click rejections
are observed immediately. Diagnostics skip a known open modal and otherwise
have a separate one-second deadline. The caption fixture reuses the accepted
browser startup and owned-child shutdown helpers, then removes only its own
temporary directory with bounded retries after all children exit.

[Controlled protocol regression](cdp-regression.log) passed: a180ms delayed
opening reliably defeats the old100ms handling and yields the original-32602
error; a blocked diagnostic expires. Event-owned cancel/accept/discard,
missing/wrong dialogs, trigger rejection, request timeout, late reply and
socket close/error cases pass. This controlled protocol reproduction does not
claim to reconstruct the original hosted browser scheduling.

[Actual caption entrypoint](actual-captions.log), [source-bound receipt](receipt.json)
and [qualification](qualification.json) passed using PostgreSQL17.6,
Python3.12.14 and Chromium151. All original edit/draft/review/reopen/filter,
keyboard review reset, repeated-submit, cancel/discard, four-record exact ZIP
and390px assertions remain. The real browser observes modal decisions
`false,true,true`. The fixture uses the existing local controlled generation
provider; it is actual app/HTTP/PostgreSQL/Chromium evidence, with no live-model
or training claim. Desktop and narrow captures are retained beside the receipt.

The existing [owned-child regression](owned-cleanup-regression.log), all three
Node syntax checks and `git diff --check` passed. [Child cleanup](cleanup.json)
confirms both owned handles exited before temporary removal.
[Schema cleanup](schema-cleanup.json) confirms the final preregistered fresh
schema was dropped and queried absent, with five records and zero workspace
Runs before disposal. The preliminary complete browser run used a different
preregistered schema, also dropped and queried absent. Its source predates the
CI-entrypoint regression call; only the final run is the source-bound acceptance.

No heavy CPU suite, performance comparison, model-quality, scientific acceptance
or CUDA claim is made. Original failures and source attributions remain intact.
Root owns independent review, serial publication/integration after PR111 and
cleanup. The task worktree `/workspace/Tuldok-captions-dialog-ci-repair-20261020`
is retained-protected by its named branch until root accepts and disposes it.
