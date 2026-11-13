'use strict';
// The controls that change the project (spec-w3.md section 3.1), and the
// plumbing every such control shares: who may use one (the rules of
// service._allowed, from the signed-in identity), a group of buttons bound to
// one key whose state outlives a re-render (waiting for an answer, the
// two-press "Confirm" state, typed text, the last refusal), and the views
// built of them: the plan view, the conflict panel, the controls of Needs
// you and the strip's Save. A control calls one operation; while it waits it
// is disabled and says so; when the answer comes what it can have changed
// is forgotten and the page reads again (hooks.changed, set by app.js); a
// refusal is shown under the control in the server's words, with its
// problems listed. Nothing is retried on its own. Text goes in through text
// nodes only.
window.LabActions = (() => {
  const P = window.TuldokProject, h = window.LabCharts.h;

  // ---- Who may use a control ------------------------------------------------
  const identity = () => (window.TuldokAuth && window.TuldokAuth.identity()) || null;
  /** Whether the session satisfies an operation's who rule (inspect, edit, cancel, request, owner). */
  function may(who) {
    const id = identity();
    if (!id || !['owner', 'agent'].includes(id.kind) || !Array.isArray(id.scopes)) return false;
    const scopes = id.scopes;
    if (who === 'inspect' || who === 'edit' || who === 'cancel') return scopes.includes(who);
    if (who === 'request') return scopes.includes('inspect') && (id.kind === 'owner' || scopes.includes('execute'));
    if (who === 'owner') return id.kind === 'owner' && scopes.includes('approve-execution');
    return false;
  }
  const isAgent = () => (identity() || {}).kind === 'agent';

  let hooks = { changed: async () => {}, refused: async () => {}, reread: async () => {} };
  /** app.js: changed() reads everything again after an answer, refused() after a refusal, reread() on request. */
  function connect(given) { hooks = Object.assign({}, hooks, given); }

  // ---- Groups of controls ----------------------------------------------------
  // A group's state, by its key: busy (the item waiting), confirming (the item
  // in its two-press state), refusal ({error, item}) and text (typed, by field).
  const slots = new Map();
  const slot = key => { if (!slots.has(key)) slots.set(key, { busy: null, confirming: null, refusal: null, text: {} }); return slots.get(key); };
  const groups = key => [...document.querySelectorAll('.act-group')].filter(g => g._key === key);
  const btn = (cls, text, key) => { const b = h('button', cls, text); b.type = 'button'; if (key) b.dataset.key = key; return b; };

  /**
   * A group of controls bound to key: an element that draws its items from
   * the group's state whenever it changes and on every re-render. An item is
   * { id, label, cls, who, op, args(slot) -> arguments (or run(slot), a step
   * of the page that throws to refuse; with local, nothing is read again
   * after it), busy (the words while
   * waiting), confirm (words: the item takes two presses), input ({name,
   * label, placeholder, max, always}: a field shown always, or in the
   * confirm state), done(result), extra(error) (more under a refusal),
   * hidden } or a plain control { id, label, cls, onClick }. Items whose who
   * the session does not satisfy are not drawn; a group with none is empty.
   * options.refusalIn: the element that shows the refusal instead of the group.
   */
  function group(key, items, options = {}) {
    const el = h('div', 'act-group' + (options.inline ? ' inline' : ''));
    el._key = key; el._items = items; el._options = options; el.dataset.group = key;
    fill(el);
    return el;
  }
  const shown = el => el._items.filter(i => !i.hidden && (!i.who || may(i.who)));
  function fill(el) {
    const key = el._key, s = slot(key), items = shown(el), opts = el._options;
    el.textContent = '';
    if (!items.length) { el.hidden = true; return; }
    el.hidden = false;
    const row = h('div', 'actions');
    const confirming = s.confirming && items.find(i => i.id === s.confirming);
    if (confirming) {
      const it = confirming;
      if (it.input && !it.input.always) el.appendChild(field(key, it.input, s));
      el.appendChild(h('p', 'confirm-words', it.confirm));
      const ok = btn('btn primary act', s.busy ? (it.busy || 'Waiting…') : 'Confirm', key + ':' + it.id + ':confirm');
      ok.disabled = !!s.busy; if (s.busy) ok.setAttribute('aria-busy', 'true');
      ok.addEventListener('click', () => press(key, it, true));
      const back = btn('btn ghost act', 'Back', key + ':' + it.id + ':back'); back.disabled = !!s.busy;
      back.addEventListener('click', () => leave(key));
      row.appendChild(ok); row.appendChild(back);
    } else {
      for (const it of items) {
        if (it.input && it.input.always) row.appendChild(field(key, it.input, s));
        const b = btn((it.cls || 'btn sm') + (it.op || it.who ? ' act' : ''), s.busy === it.id ? (it.busy || 'Waiting…') : it.label, key + ':' + it.id);
        if (it.title) b.title = it.title;
        if (s.busy) { b.disabled = true; if (s.busy === it.id) b.setAttribute('aria-busy', 'true'); }
        b.addEventListener('click', () => it.onClick ? it.onClick() : press(key, it, false));
        row.appendChild(b);
      }
    }
    el.appendChild(row);
    const host = opts.refusalIn || el;
    if (opts.refusalIn) opts.refusalIn.textContent = '';
    if (s.refusal && items.some(i => i.id === s.refusal.item)) {
      const it = items.find(i => i.id === s.refusal.item);
      host.appendChild(refusal(s.refusal.error, it.extra ? it.extra(s.refusal.error) : null));
    }
  }
  function field(key, input, s) {
    const l = h('label', 'act-field');
    l.appendChild(document.createTextNode(input.label));
    const area = input.lines ? h('textarea') : h('input');
    if (input.lines) area.rows = input.lines; else area.type = 'text';
    if (input.max) area.maxLength = input.max;
    if (input.placeholder) area.placeholder = input.placeholder;
    area.value = s.text[input.name] || ''; area.dataset.key = key + ':field:' + input.name; area.disabled = !!s.busy;
    area.autocomplete = 'off'; area.spellcheck = false;
    area.addEventListener('input', () => { s.text[input.name] = area.value; });
    area.addEventListener('keydown', e => { if (e.key === 'Enter' && !input.lines) { e.preventDefault(); const b = area.closest('.act-group').querySelector('button.act'); if (b && !b.disabled) b.click(); } });
    l.appendChild(area);
    if (input.max && input.max <= 1000) l.appendChild(h('span', 'hint', 'at most ' + input.max + ' characters'));
    return l;
  }
  function refill(key) { for (const g of groups(key)) fill(g); }
  function focusKey(dataKey) { const e = [...document.querySelectorAll('[data-key]')].find(x => x.dataset.key === dataKey && x.offsetParent !== null); if (e) { e.focus(); return true; } return false; }
  function leave(key) { const s = slot(key), was = s.confirming; s.confirming = null; refill(key); if (was) focusKey(key + ':' + was); }
  /** Escape: leaves every two-press state not waiting for its answer; true when one was left. */
  function escape() {
    let left = false;
    for (const [key, s] of slots) if (s.confirming && !s.busy) { leave(key); left = true; }
    return left;
  }
  async function press(key, it, confirmed) {
    const s = slot(key);
    if (s.busy) return;
    if (it.confirm && !confirmed) { s.confirming = it.id; s.refusal = null; refill(key); focusKey(key + ':' + (it.input && !it.input.always ? 'field:' + it.input.name : it.id + ':confirm')); return; }
    s.busy = it.id; s.refusal = null; refill(key);
    let result, error = null;
    // run(slot): a step of the page itself (editor.js), which may call operations; it throws to refuse.
    try { result = it.run ? await it.run(s) : await P.call(it.op, it.args ? it.args(s) : {}); } catch (e) { error = e; }
    s.busy = null;
    if (error) {
      s.refusal = { error, item: it.id }; refill(key);
      focusKey(key + ':' + it.id) || focusKey(key + ':' + it.id + ':confirm');
      if (!it.local) await hooks.refused({ key, item: it, error });
      return;
    }
    s.confirming = null; s.text = {}; refill(key);
    // local: nothing in the project changed, so nothing is read again.
    if (it.local) { if (it.done) it.done(result); return; }
    P.forgetBut(P.WATCHED);   // what it can have changed is read afresh; the watched answers are read again by hooks.changed and compared
    if (it.done) it.done(result);
    await hooks.changed({ key, item: it, result, focus: key + ':' + it.id });
  }

  /** A refusal in the server's words: its sentence, its problems, what it names; extra under them. */
  function refusal(error, extra) {
    const box = h('div', 'failure refusal'); box.setAttribute('role', 'alert');
    box.appendChild(h('p', null, error.message || String(error)));
    const problems = error.problems || [];
    if (problems.length) {
      const ul = h('ul');
      for (const p of problems) {
        const where = [p.path, p.pointer].filter(x => x && x !== '/').join(' ');
        ul.appendChild(h('li', null, (p.severity === 'warning' ? 'Warning: ' : '') + (where ? where + ': ' : '') + (p.message || '')));
      }
      box.appendChild(ul);
    }
    if (error.references && error.references.length) box.appendChild(h('p', 'small', 'Named: ' + error.references.join(', ') + '.'));
    if (error.files && error.files.length) box.appendChild(h('p', 'small', 'Files: ' + error.files.join(', ') + '.'));
    if (extra) box.appendChild(extra);
    return box;
  }

  // ---- The strip's Save and the controls of Needs you ---------------------------
  const plural = (n, one, many) => n + ' ' + (n === 1 ? one : many);
  /** Save, with a refusal changed-on-disk offering to read the project again. */
  const saveItem = () => ({
    id: 'save', label: 'Save', cls: 'btn sm', who: 'edit', op: 'save', busy: 'Saving…',
    extra: error => { if (error.code !== 'changed-on-disk') return null; const b = btn('btn sm', 'Read the project again', 'reread'); b.addEventListener('click', () => hooks.reread()); const d = h('div', 'actions'); d.appendChild(b); return d; }
  });
  /** The strip's part: how many definitions are unsaved or marked removed, and Save. */
  function stripSave(status, note) {
    const n = status.unsaved.length + status.removed.length;
    if (!n) { if (note) note.textContent = ''; return null; }
    const box = h('span', 'unsaved');
    box.appendChild(h('span', 'count', plural(n, 'definition', 'definitions') + ' unsaved'));
    box.appendChild(group('save', [saveItem()], { inline: true, refusalIn: note }));
    return box;
  }
  /** The controls under one item of Needs you (adapter.needs): go(screen, id) opens a place. */
  function needControls(n, go) {
    const items = [];
    if (n.request) {
      const id = n.request.id;
      items.push({ id: 'approve', label: 'Approve', cls: 'btn sm primary', who: 'owner', op: 'approve_build', args: () => ({ request: id }), busy: 'Approving…' });
      items.push(declineItem(id));
      items.push({ id: 'open', label: 'Open on Train', cls: 'btn sm ghost', onClick: () => go('train', 'request:' + id) });
    } else if (n.save) {
      items.push(saveItem());
      for (const ref of n.references.slice(0, 6)) {
        const where = ref.startsWith('recipes/') ? 'map' : ref.startsWith('datasets/') ? 'data' : null;
        if (where) items.push({ id: 'open-' + ref, label: ref, cls: 'btn sm ghost', onClick: () => go(where, ref) });
      }
    } else if (n.environment) {
      const e = n.environment;
      if (e.interpreter) items.push(checkItem(e.reference));
      items.push({ id: 'open', label: 'On Train', cls: 'btn sm ghost', onClick: () => go('train', 'env:' + e.reference) });
    } else if (n.run) {
      items.push({ id: 'run', label: 'The run', cls: 'btn sm ghost', onClick: () => go('train', 'run:' + n.run.id) });
      items.push({ id: 'plan', label: 'Plan build', cls: 'btn sm', who: 'request', onClick: () => go('train', 'plan:' + n.reference) });
    }
    if (!items.length) return null;
    return group('need:' + (n.save ? 'save' : n.key), items);
  }
  const declineItem = id => ({ id: 'decline', label: 'Decline', cls: 'btn sm', who: 'owner', op: 'decline_build', busy: 'Declining…',
    confirm: 'Decline this request; the reason is kept with it and shown to whoever asked.',
    input: { name: 'reason', label: 'Reason (optional)', max: 400, lines: 2 },
    args: s => ({ request: id, reason: (s.text.reason || '').trim() }) });
  const checkItem = reference => ({ id: 'check', label: 'Check again', cls: 'btn sm', who: 'edit', op: 'check_environment', args: () => ({ reference }), busy: 'Checking…' });

  // ---- The plan view ------------------------------------------------------------
  const ACTION = {
    build: ['pending', 'Build'], built: ['good', 'Built already'], ready: ['good', 'Ready'],
    'set-up': ['warn', 'Set up first'], blocked: ['serious', 'Blocked']
  };
  const gb = x => (x >= 100 ? Math.round(x) : x >= 1 ? x.toFixed(1) : x >= 0.01 ? x.toFixed(2) : x > 0 ? x.toExponential(1) : '0') + ' GB';
  const hours = x => x >= 1 ? x.toFixed(1) + ' h' : x * 60 >= 1 ? Math.round(x * 60) + ' min' : x > 0 ? Math.max(1, Math.round(x * 3600)) + ' s' : '0 h';
  /** What one step would do, in sentences. */
  function stepWords(st) {
    const out = [];
    if (st.action === 'build') {
      out.push({ 'not-built': 'Not built yet: it will be built.', 'out-of-date': 'Out of date: it will be built again.', failed: 'Its last run failed: it will be built again.', running: 'Running now: a build will not start it a second time.' }[st.state] || 'It will be built.');
      for (const r of st.reasons || []) out.push(r);
    } else if (st.action === 'built') out.push('Built already' + (st.adopted ? ' (adopted)' : '') + (st.scratch ? ', by a run from the code as it was on disk' : '') + ': nothing to do.');
    else if (st.action === 'ready') out.push('Ready on this machine.');
    else if (st.action === 'set-up') out.push(st.state === 'failing' ? 'Its last check failed: check it or connect another interpreter on Train before building.' : 'Not set up on this machine: connect an interpreter on Train, or set it up from the command line, before building.');
    else if (st.action === 'blocked') {
      if (!st.blocked_by.length) out.push(st.kind === 'benchmark' ? 'Blocked: none of its subjects would run.' : 'Blocked.');
      for (const c of st.blocked_by) out.push('Blocked: ' + (c.reference === st.reference ? 'it is' : c.reference + ' is') + ' labelled rebuild ' + c.rebuild + (c.reason ? ' (' + c.reason + ')' : '') + '.');
      if (st.blocked_by_more) out.push('And ' + plural(st.blocked_by_more, 'more cause', 'more causes') + '.');
    }
    const uses = Object.entries(st.inputs || {}).map(([name, i]) => name + ' from ' + i.reference + (i.output ? ' (' + i.output + ')' : ''));
    if (uses.length) out.push('Uses ' + uses.join(', ') + '.');
    if (st.environment && st.kind !== 'environment') out.push('Runs in ' + st.environment + '.');
    if (st.subjects) {
      if (st.subjects.run.length) out.push('Runs the subjects ' + st.subjects.run.join(', ') + '.');
      for (const k of st.subjects.skipped) out.push('Skips ' + k.name + ': ' + k.reason + '.');
    }
    if (st.action === 'build') {
      const r = st.resources || {}, said = [];
      if (r.gpu === true) said.push('uses the GPU');
      if (typeof r.disk_gb === 'number') said.push(gb(r.disk_gb) + ' of disk'); if (typeof r.wall_hours === 'number') said.push(hours(r.wall_hours));
      out.push(said.length ? 'Declares: ' + said.join(', ') + '.' : 'Declares no GPU, disk or time.');
      const e = st.estimate;
      if (e) { const est = []; if (e.disk_bytes != null) est.push(gb(e.disk_bytes / 1e9) + ' of disk'); if (e.wall_seconds != null) est.push(hours(e.wall_seconds / 3600)); if (est.length) out.push('Estimated: ' + est.join(', ') + '.'); }
    }
    return out;
  }
  /** The totals of a plan: GPU steps, disk and time as stated, estimated or unknown. */
  function totals(plan) {
    const n = plan.counts.build, out = [];
    if (!n) return ['Nothing would be built, so there are no totals.'];
    out.push('To build: ' + plural(n, 'step', 'steps') + ', ' + (plan.gpu_steps ? plan.gpu_steps + ' of them on the GPU' : 'none on the GPU') + '.');
    for (const [name, sum, unknown, est, estSteps, fmt] of [['Disk', plan.disk_gb, plan.disk_unknown, plan.estimated_disk_gb, plan.estimated_disk_steps, gb], ['Time', plan.wall_hours, plan.wall_unknown, plan.estimated_wall_hours, plan.estimated_wall_steps, hours]]) {
      let t = name + ': ' + (unknown === n ? 'unknown, no step states it' : fmt(sum) + ' stated' + (unknown ? '; ' + unknown + ' of ' + n + ' state none, so it is more' : ''));
      t += estSteps ? '; estimated ' + fmt(est) + ' for ' + plural(estSteps, 'step', 'steps') + ' that were measured.' : '; no estimate was measured.';
      out.push(t);
    }
    out.push('The figures are as the definitions state them; nothing was run to make this plan.');
    return out;
  }
  /**
   * The plan view in the drawer, for sel 'plan:<target>,<target>' or
   * 'plan:*' (everything buildable): read with `plan`, shown in sentences,
   * with the scratch box and Request build. back(): leaves the view. Read
   * again for the plan on screen (aside._again), it stays until the new one
   * is built off the page and put in its place in one step.
   */
  function planView(aside, sel, go, back) {
    if (aside._for === sel && !aside._again) return;
    const S = window.LabScreens, same = aside._for === sel && !!aside.firstChild, mine = S.parts.turn(aside), live = () => aside._turn === mine && aside._for === sel;
    aside._for = sel;
    const every = sel === 'plan:*', targets = every ? [] : sel.slice(5).split(',').filter(Boolean);
    if (!same) { aside.textContent = ''; aside.appendChild(h('p', 'note', 'Reading…')); }
    P.read('plan', { targets, every }).then(plan => {
      if (!live()) return;
      const ins = h('div', 'inspector plan-view');
      const hd = h('header'); hd.appendChild(h('span', 'kicker', 'plan · nothing runs until it is requested'));
      const title = h('h2', null, every ? 'A build of everything buildable' : 'A build of ' + plan.targets.join(', ')); title.tabIndex = -1; hd.appendChild(title);
      const c = plan.counts, meta = h('div', 'ins-meta');
      meta.appendChild(window.LabScreens.stateEl(plan.buildable ? (c.build ? 'good' : 'neutral') : 'serious', plan.buildable ? (c.build ? 'can be built' : 'nothing to build') : 'cannot be built'));
      hd.appendChild(meta); ins.appendChild(hd);
      if (back) { const a = h('div', 'actions'); const b = btn('btn sm ghost', '← Back', 'plan-back'); b.addEventListener('click', back); a.appendChild(b); ins.appendChild(a); }
      const parts = [plural(c.build, 'step', 'steps') + ' to build', c['set-up'] + ' to set up', c.blocked + ' blocked'];
      if (c.ready) parts.push(plural(c.ready, 'environment', 'environments') + ' ready');
      if (c.built) parts.push(c.built + ' built already');
      ins.appendChild(h('p', 'plan-lead', parts.join(', ') + ': ' + (plan.buildable ? (every ? 'everything buildable' : plan.targets.join(', ')) + (c.build ? ' can be built.' : ' is built already.') : (plan.blocked_targets.join(', ') + (plan.blocked_targets.length === 1 ? ' cannot' : ' cannot') + ' be built.'))));
      if (plan.blocked_targets.length) ins.appendChild(h('p', 'failure', 'Blocked ' + (plan.blocked_targets.length === 1 ? 'target' : 'targets') + ': ' + plan.blocked_targets.join(', ') + '. A build is refused while any target is blocked; the steps below say why.'));
      const d = h('div'); d.appendChild(h('h3', null, 'Steps, in the order they would run'));
      if (!plan.steps.length) d.appendChild(h('p', 'note', 'No step: nothing here is built by Tuldok.'));
      const ol = h('ol', 'steps');
      for (const st of plan.steps) {
        const [tone, word] = ACTION[st.action] || ['neutral', st.action];
        const li = h('li', st.action === 'build' ? 'todo' : st.action === 'blocked' ? 'blocked' : 'done'); li.dataset.step = st.reference;
        li.appendChild(window.LabScreens.stateEl(tone, ''));
        const t = h('span'); t.appendChild(h('span', 'title', st.number + '. ' + word + ' · ' + (st.title || st.reference)));
        t.appendChild(h('span', 'sub mono', st.reference + (st.action === 'build' && st.resources && st.resources.gpu === true ? ' · GPU' : '')));
        for (const line of stepWords(st)) t.appendChild(h('span', 'sub', line));
        li.appendChild(t); ol.appendChild(li);
      }
      d.appendChild(ol); ins.appendChild(d);
      const tt = h('div'); tt.appendChild(h('h3', null, 'What it takes')); for (const line of totals(plan)) tt.appendChild(h('p', 'small', line)); ins.appendChild(tt);
      if (plan.notes.length) { const nd = h('div'); nd.appendChild(h('h3', null, 'Notes')); for (const n of plan.notes) nd.appendChild(h('p', 'small', n)); ins.appendChild(nd); }
      if (may('request')) {
        const key = 'request:' + sel, s = slot(key);
        const f = h('div', 'form');
        const lab = h('label', 'check'); const box = h('input'); box.type = 'checkbox'; box.checked = !!s.text.scratch; box.dataset.key = key + ':scratch';
        box.addEventListener('change', () => { s.text.scratch = box.checked; });
        lab.appendChild(box); lab.appendChild(document.createTextNode(' Run from the code as it is on disk; the product is marked scratch'));
        f.appendChild(lab); ins.appendChild(f);
        const label = isAgent() ? 'Ask the owner for this build' : 'Request build';
        ins.appendChild(group(key, [{ id: 'request', label, cls: 'btn primary', who: 'request', op: 'request_build', busy: isAgent() ? 'Asking…' : 'Requesting…',
          args: st => ({ targets, every, scratch: !!st.text.scratch }), done: r => go('train', 'request:' + r.id) }]));
        ins.appendChild(h('p', 'note', isAgent() ? 'The owner approves or declines what you ask for; nothing runs before.' : 'Your request is queued at once and runs when the build worker takes it.'));
      }
      S.parts.putDrawer(aside, ins);
    }, error => { if (live()) S.parts.putDrawer(aside, refusal(error)); });
  }

  // ---- The conflict panel --------------------------------------------------------
  /** The main area when a read was refused conflict: the server's sentence, the definitions, and the two ways out. */
  function conflictPanel(main, error) {
    const sec = h('section', 'conflict');
    const t = h('h2', null, 'Files changed on disk where Tuldok holds unsaved edits'); t.tabIndex = -1; sec.appendChild(t);
    sec.appendChild(h('p', null, error.message));
    const refs = error.references || [];
    if (refs.length) { const ul = h('ul', 'conflict-refs'); for (const r of refs) ul.appendChild(h('li', 'mono', r)); sec.appendChild(ul); }
    sec.appendChild(h('p', 'note', 'Keep my edits: the unsaved edits stay and replace those files when you save. Take the files: the unsaved edits of ' + (refs.length === 1 ? 'this definition are' : 'these definitions are') + ' dropped and the files are read as they are now.'));
    const g = group('conflict', [
      { id: 'keep', label: 'Keep my edits', cls: 'btn primary', who: 'edit', op: 'resolve_conflict', args: () => ({ choice: 'keep' }), busy: 'Keeping…' },
      { id: 'discard', label: 'Take the files', cls: 'btn', who: 'edit', op: 'resolve_conflict', args: () => ({ choice: 'discard' }), busy: 'Taking the files…',
        confirm: 'Drop the unsaved edits of ' + (refs.length ? refs.join(', ') : 'these definitions') + ' and take the files on disk.' }
    ]);
    sec.appendChild(g);
    if (g.hidden) sec.appendChild(h('p', 'note', 'Someone who may edit this project has to choose; until then the project cannot be read.'));
    main.appendChild(sec);
  }

  return { may, isAgent, connect, group, slot, escape, refusal, stripSave, needControls, planView, conflictPanel, declineItem, checkItem, focusKey };
})();
