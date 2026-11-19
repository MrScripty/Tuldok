'use strict';
// Serving a trained model on the page (docs/plans/training-and-curation/spec-t6.md section 7): the Train tab's
// Served models (a row per recipe that declares serve, opening its serving drawer, serve:<recipe>), and a Serving
// block in a model's drawer on the Map. Each panel shows the model's state, the endpoint's address, the controls
// (Serve, or Ask the owner to serve it; Approve and Decline; Stop, in two presses), the output's tail of a failure,
// the session's timing summary and Try it: the inputs as JSON, Send, and the answer of POST /api/serve/<name>/predict.
//
// Updating in place (spec-w4): a control's answer reads the project again as every control does (actions.js). While a
// panel or a row on the page shows a session starting or awaiting approval, `served` is asked every second and each
// one's state mark, line and controls are set in place, its Try it shown once it is ready; nothing else is read again
// and nothing is rebuilt. Try it reads nothing of the project; after an answer the panel's timing summary is read
// again (serve_session) and set in place.
window.LabServing = (() => {
  const P = window.TuldokProject, S = window.LabScreens, A = window.LabActions, h = window.LabCharts.h;
  const POLL_MS = 1000, SHOWN = 4000;
  const TONE = { 'awaiting-approval': ['warn', 'awaiting approval'], starting: ['pending', 'starting'], ready: ['good', 'ready'],
    failed: ['serious', 'failed'], stopped: ['neutral', 'stopped'], declined: ['neutral', 'declined'], expired: ['neutral', 'expired'] };
  const OPEN = ['awaiting-approval', 'starting', 'ready'], WAITING = ['awaiting-approval', 'starting'];
  const nameOf = ref => ref.slice(ref.indexOf('/') + 1);
  const address = ref => 'POST /api/serve/' + nameOf(ref) + '/predict';
  const ms = v => v == null ? '—' : v < 10 ? v.toFixed(2) + ' ms' : v < 1000 ? v.toFixed(1) + ' ms' : (v / 1000).toFixed(2) + ' s';
  const button = (cls, text, key, onClick) => { const b = h('button', cls, text); b.type = 'button'; if (key) b.dataset.key = key; if (onClick) b.addEventListener('click', onClick); return b; };
  const current = item => item.session && OPEN.includes(item.session.state) ? item.session : null;

  /** {tone, word, line} of a servable model: its open session, else its last one, else whether it can be served. */
  function standing(item) {
    const s = item.session;
    if (s && OPEN.includes(s.state)) {
      const [tone, word] = TONE[s.state];
      const line = s.state === 'ready' ? s.requests + (s.requests === 1 ? ' request' : ' requests') + (s.failed_requests ? ', ' + s.failed_requests + ' failed' : '') + ' · stops after ' + s.idle_minutes + ' min idle'
        : s.state === 'starting' ? 'loading its product in ' + (s.environment || 'its environment')
        : 'asked by ' + ((s.requested_by && (s.requested_by.label || s.requested_by.kind)) || 'someone') + '; the owner approves it';
      return { tone, word, line };
    }
    if (s) { const [tone, word] = TONE[s.state] || ['neutral', s.state]; return { tone, word, line: (s.reason || s.problem || '') + (item.built ? '' : ' · not built') }; }
    return item.built ? { tone: 'neutral', word: 'not served', line: 'built; it can be served' } : { tone: 'neutral', word: 'not served', line: 'not built: build it before serving it' };
  }
  function controls(item) {
    const s = current(item), ref = item.model;
    const items = [];
    if (!s && item.built) items.push({ id: 'serve', label: A.may('owner') ? 'Serve' : 'Ask the owner to serve it', cls: 'btn sm primary', who: 'request', op: 'serve_start', args: () => ({ model: ref }), busy: 'Starting…' });
    if (s && s.state === 'awaiting-approval') {
      items.push({ id: 'approve', label: 'Approve', cls: 'btn sm primary', who: 'owner', op: 'serve_approve', args: () => ({ session: s.id }), busy: 'Approving…' });
      items.push({ id: 'decline', label: 'Decline', cls: 'btn sm', who: 'cancel', op: 'serve_stop', args: () => ({ session: s.id }), busy: 'Declining…', confirm: 'Decline serving this model; nothing is started.' });
    }
    if (s && (s.state === 'starting' || s.state === 'ready'))
      items.push({ id: 'stop', label: 'Stop', cls: 'btn sm', who: 'cancel', op: 'serve_stop', args: () => ({ session: s.id }), busy: 'Stopping…', confirm: 'Stop serving this model; requests to it are refused from then on.' });
    return A.group('serve:' + ref + ':' + (s ? s.id + ':' + s.state : 'none'), items, { inline: true });
  }

  // ---- In place --------------------------------------------------------------------------------------------------
  /** Sets the state of every row and panel of item.model on the page from item, in place. */
  function update(item) {
    for (const el of document.querySelectorAll('[data-serve-model]')) {
      if (el.dataset.serveModel !== item.model || !el._serve) continue;
      el._serve(item);
    }
  }
  let timer = null;
  function watch() {
    if (timer) return;
    timer = setTimeout(async () => {
      timer = null;
      const waiting = [...document.querySelectorAll('[data-serve-model]')].filter(el => el.isConnected && WAITING.includes(el.dataset.serveState));
      if (!waiting.length) return;
      try { const served = await P.call('served'); for (const item of served.servable) update(item); } catch (error) { /* asked again on the next tick */ }
      watch();
    }, POLL_MS);
  }
  /** The state mark and line of an element: replaced only when they differ. */
  function paintState(el, mark, line, item) {
    const st = standing(item), stateKey = st.tone + ' ' + st.word;
    if (mark._key !== stateKey) { const fresh = S.stateEl(st.tone, st.word); fresh._key = stateKey; fresh.classList.add('srv-mark'); mark.replaceWith(fresh); mark = fresh; }
    if (line.textContent !== st.line) line.textContent = st.line;
    el.dataset.serveState = item.session ? item.session.state : 'none';
    if (WAITING.includes(el.dataset.serveState)) watch();
    return mark;
  }

  // ---- Train: Served models ------------------------------------------------------------------------------------------
  function section(frag, served, sel, act) {
    const head = S.parts.sect('Served models', served.error ? '' : served.servable.length + ' declare serve · at most ' + served.most + ' at once'); head.classList.add('gap');
    frag.appendChild(head);
    if (served.error) { frag.appendChild(A.refusal(served.error)); return; }
    if (!served.servable.length) { frag.appendChild(h('p', 'empty', 'No recipe declares serve. A recipe serves its model through its own serve.py (see the project format).')); return; }
    const ul = h('ul', 'rows srv-rows');
    for (const item of served.servable) {
      const key = 'serve:' + item.model, li = h('li'), b = button('row env srv-row', null, 'open-' + key, () => act.select(sel === key ? null : key));
      b.setAttribute('aria-pressed', String(sel === key)); b.dataset.serveModel = item.model;
      let mark = h('span'); b.appendChild(mark);
      const t = h('span'), line = h('span', 'sub'); t.appendChild(h('span', 'title', item.title)); t.appendChild(line); b.appendChild(t);
      b.appendChild(h('span', 'sub mono', nameOf(item.model) + ' · ' + item.module_file));
      b._serve = it => { mark = paintState(b, mark, line, it); };
      b._serve(item);
      li.appendChild(b); ul.appendChild(li);
    }
    frag.appendChild(ul);
  }

  // ---- A panel: the drawer and the block ------------------------------------------------------------------------------
  /** The panel of one servable item, updated in place by _serve(item). */
  function panel(item, heading) {
    const box = h('section', 'srv'); box.dataset.serveModel = item.model;
    if (heading) box.appendChild(h('h3', null, heading));
    const head = h('div', 'srv-head'); let mark = h('span'); const line = h('span', 'small srv-line'); head.appendChild(mark); head.appendChild(line); box.appendChild(head);
    const where = h('p', 'small mono srv-address', address(item.model)); box.appendChild(where);
    const acts = h('div', 'srv-acts'); box.appendChild(acts);
    const fail = h('div', 'srv-fail'); fail.hidden = true; box.appendChild(fail);
    const times = h('div', 'srv-times'); times.hidden = true; box.appendChild(times);
    const tryBox = tryIt(item, () => box._times()); tryBox.hidden = true; box.appendChild(tryBox);
    let cur = item, shown = null;
    box._times = async () => {
      const s = cur.session;
      if (!s) { times.hidden = true; return; }
      let found;
      try { found = await P.call('serve_session', { session: s.id }); } catch (error) { times.hidden = true; return; }
      if (cur.session && cur.session.id === found.id) {   // the counts of the line, as the summary has them
        cur = Object.assign({}, cur, { session: Object.assign({}, cur.session, { requests: found.requests, failed_requests: found.failed_requests }) });
        mark = paintState(box, mark, line, cur);
      }
      paintTimes(times, found);
    };
    box._serve = it => {
      cur = it;
      mark = paintState(box, mark, line, it);
      const s = it.session, now = (s ? s.id + ':' + s.state : 'none') + ':' + it.built;
      if (now === shown) return;   // the controls, the failure and Try it change with the state only
      shown = now;
      acts.replaceChildren(controls(it));
      const failed = s && s.state === 'failed';
      fail.hidden = !failed; fail.replaceChildren();
      if (failed) { fail.appendChild(h('p', 'small', s.problem || 'It failed.')); if (s.output_tail) { const pre = h('pre', 'evtext srv-tail'); pre.textContent = s.output_tail; fail.appendChild(pre); } }
      tryBox.hidden = !(s && s.state === 'ready');
      box._times();
    };
    box._serve(item);
    return box;
  }
  function paintTimes(times, found) {
    const sum = found.summary;
    times.hidden = !sum.count;
    if (!sum.count) return;
    const dl = h('dl', 'facts srv-summary');
    const put = (k, v) => { dl.appendChild(h('dt', null, k)); dl.appendChild(h('dd', 'num', v)); };
    put('Requests', sum.count + (sum.failed ? ' (' + sum.failed + ' failed)' : '') + (sum.throughput_per_second != null ? ' · ' + sum.throughput_per_second.toFixed(1) + ' a second' : ''));
    for (const [k, title] of [['total_ms', 'Total'], ['model_ms', 'Model'], ['queue_ms', 'Queue']]) if (sum[k]) put(title, 'p50 ' + ms(sum[k].p50) + ' · p95 ' + ms(sum[k].p95) + ' · p99 ' + ms(sum[k].p99));
    times.replaceChildren(h('h4', null, 'This session'), dl);
  }
  /** Try it: the inputs as JSON, Send, and the answer; nothing of the project is read again. */
  function tryIt(item, after) {
    const box = h('div', 'srv-try'), ref = item.model;
    box.appendChild(h('h4', null, 'Try it'));
    const area = h('textarea', 'srv-inputs'); area.rows = 4; area.spellcheck = false; area.dataset.key = 'serve-inputs-' + ref; area.setAttribute('aria-label', 'Inputs as JSON');
    area.value = JSON.stringify(item.example || {});
    const out = h('div', 'srv-answer'); out.setAttribute('aria-live', 'polite');
    const send = button('btn sm primary', 'Send', 'serve-send-' + ref, async () => {
      let inputs;
      try { inputs = JSON.parse(area.value); if (!inputs || typeof inputs !== 'object' || Array.isArray(inputs)) throw Error('The inputs must be a JSON object.'); }
      catch (error) { out.replaceChildren(A.refusal(Error(error.message))); return; }
      send.disabled = true; send.textContent = 'Sending…'; send.setAttribute('aria-busy', 'true');
      try {
        const response = await window.TuldokAuth.fetch('/api/serve/' + nameOf(ref) + '/predict', { method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ inputs }) });
        let value; try { value = await response.json(); } catch (e) { value = { error: 'The server answered ' + response.status + ' without JSON.' }; }
        if (!response.ok) throw Object.assign(Error(value.error || 'Refused.'), { code: value.code });
        const text = JSON.stringify(value.outputs, null, 1), pre = h('pre', 'evtext srv-outputs');
        pre.textContent = text.length > SHOWN ? text.slice(0, SHOWN) + '\n…' : text;
        out.replaceChildren(h('p', 'small srv-timing', 'total ' + ms(value.timing.total_ms) + ' · model ' + ms(value.timing.model_ms) + ' · queue ' + ms(value.timing.queue_ms)), pre);
        after();
      } catch (error) { out.replaceChildren(A.refusal(error)); }
      finally { send.disabled = false; send.textContent = 'Send'; send.removeAttribute('aria-busy'); }
    });
    const row = h('div', 'actions'); row.appendChild(send);
    box.appendChild(area); box.appendChild(row); box.appendChild(out);
    box.appendChild(h('p', 'note', 'Arrays may be written as {"array": "float32", "shape": […], "base64": "…"}; the answer is shown as it came.'));
    return box;
  }

  /** The Train tab's drawer of one servable model (serve:<recipe>). */
  function drawer(aside, key, act) {
    const ref = key.slice(6);
    if (aside._for === key && !aside._again) return;
    aside._for = key;
    P.call('served').then(served => {
      if (aside._for !== key) return;
      const item = served.servable.find(x => x.model === ref);
      const ins = h('div', 'inspector'), hd = h('header');
      hd.appendChild(h('span', 'kicker', 'serving · ' + nameOf(ref)));
      const t = h('h2', null, item ? item.title : ref); t.tabIndex = -1; hd.appendChild(t); ins.appendChild(hd);
      if (!item) ins.appendChild(h('p', 'empty', ref + ' declares no serve.'));
      else {
        const go = h('div', 'actions'); go.appendChild(button('btn sm ghost', 'On the map', null, () => act.go('map', ref))); ins.appendChild(go);
        ins.appendChild(panel(item, null));
        const dl = h('dl', 'facts');
        for (const [k, v] of [['Entry point', item.module_file], ['Environment', item.environment || '—'], ['Product', item.product_run ? 'run ' + item.product_run.slice(0, 8) : 'none'], ['Idle stop', item.idle_minutes + ' min']]) { dl.appendChild(h('dt', null, k)); dl.appendChild(h('dd', 'mono', v)); }
        ins.appendChild(dl);
      }
      S.parts.putDrawer(aside, ins);
    }, error => { if (aside._for !== key) return; const frag = document.createDocumentFragment(); frag.appendChild(A.refusal(error)); S.parts.putDrawer(aside, frag); });
  }

  /** The Serving block of a model's drawer (screens.js): shown only for a model whose recipe declares serve. */
  async function block(box, m, live) {
    const served = await P.call('served');
    if (!live()) return;
    const item = served.servable.find(x => x.model === m.id);
    if (!item) { box.hidden = true; return; }
    box.replaceChildren(panel(item, 'Serving'));
    box.hidden = false;
  }

  return { section, drawer, block };
})();
