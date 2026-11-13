'use strict';
// Editing and branching (spec-w3.md section 3.2, slice T22): the editor in the
// drawer, with two views of one text (Text for every kind, Form for a
// recipe); Keep, Discard edit, Remove and Save through actions.js; Pick on the
// map; Branch from here and the drafts it makes; the steps of a new model; the
// Overview's list of every definition. What is typed is kept in page memory
// per definition until it is kept or discarded, so leaving the drawer or a
// re-render loses nothing, and a reading on the timer or on focus leaves the
// editor and the branch form alone; a draft is kept in sessionStorage under the
// project's id, so it survives a reload of the tab. The form changes only the
// fields touched and writes the JSON back with the indentation the text had.
// Nothing here writes to disk: Keep stores an unsaved edit, Save writes them.
// Text goes in through text nodes only.
window.LabEditor = (() => {
  const P = window.TuldokProject, A = window.LabActions, S = window.LabScreens, Tree = window.LabTree, h = window.LabCharts.h;
  const { sect, modelState } = S.parts;
  const isObject = v => !!v && typeof v === 'object' && !Array.isArray(v);
  const button = (cls, text, key, onClick) => { const b = h('button', cls, text); b.type = 'button'; if (key) b.dataset.key = key; if (onClick) b.addEventListener('click', onClick); return b; };
  const KIND_ORDER = ['recipe', 'dataset', 'model', 'step', 'benchmark', 'chart', 'environment'];
  const KIND_TITLE = { recipe: 'Recipes', dataset: 'Datasets', model: 'Models', step: 'Steps', benchmark: 'Benchmarks', chart: 'Charts', environment: 'Environments' };

  // ---- Page memory ------------------------------------------------------------
  const buffers = new Map();   // reference -> { text, base }: typed and not kept yet
  const views = new Map();     // reference -> 'form' | 'text'
  let drafts = [];             // { reference, parent, text, inlined, problems }: branches not kept yet
  let followed = [];           // references branched in this tab and kept: their drawer keeps the steps
  let project = null, picking = null, pickNote = '', current = null;

  const storeKey = () => 'tuldok-drafts:' + project;
  function persist() { if (!project) return; try { sessionStorage.setItem(storeKey(), JSON.stringify({ drafts, followed })); } catch (e) { /* kept for this page only */ } }
  const validDraft = d => isObject(d) && typeof d.reference === 'string' && d.reference.startsWith('recipes/') && typeof d.parent === 'string' && typeof d.text === 'string';
  /** app.js, once the summary is read: the drafts of this project kept in this tab. */
  function load(id) {
    if (project === id) return;
    project = id;
    let saved = null; try { saved = JSON.parse(sessionStorage.getItem(storeKey()) || 'null'); } catch (e) { saved = null; }
    drafts = saved && Array.isArray(saved.drafts) ? saved.drafts.filter(validDraft).map(d => ({ reference: d.reference, parent: d.parent, text: d.text, inlined: typeof d.inlined === 'string' ? d.inlined : null, problems: Array.isArray(d.problems) ? d.problems : [] })) : [];
    followed = saved && Array.isArray(saved.followed) ? saved.followed.filter(x => typeof x === 'string') : [];
    publish();
  }
  /** What the map draws of each draft (adapter.js); a draft whose parent is gone, or whose reference is taken, is dropped. */
  function publish() { P.setDrafts(drafts.map(drawn), dropped); }
  function dropped(gone) {
    const refs = new Set(gone.map(d => d.reference));
    drafts = drafts.filter(d => !refs.has(d.reference)); persist(); P.setDrafts(drafts.map(drawn));
  }
  function drawn(d) {
    const doc = parse(d.text).doc || {}, str = v => typeof v === 'string' ? v : null;
    return { reference: d.reference, parent: d.parent, title: str(doc.title) || d.reference.slice(8), short: isObject(doc.labels) ? str(doc.labels.short) : null,
      description: str(doc.description), group: str(doc.group), change: str(doc.change) };
  }
  const draftOf = ref => drafts.find(d => d.reference === ref) || null;
  const isDraft = ref => A.may('edit') && !!draftOf(ref);

  // ---- One text ---------------------------------------------------------------------
  function parse(text) {
    try { const doc = JSON.parse(text); return isObject(doc) ? { doc } : { error: 'The text is JSON but not an object.' }; }
    catch (e) { return { error: e.message }; }
  }
  /** The indentation of the text: that of its first indented line, else two spaces. */
  const indentOf = text => { const m = /\n([ \t]+)\S/.exec(text || ''); return m ? m[1] : '  '; };
  const textOf = (ref, def) => { const d = draftOf(ref); return buffers.has(ref) ? buffers.get(ref).text : d ? d.text : def ? def.text : ''; };
  /** Keeps typed text: a draft's own text, else a buffer until it is kept or discarded (none when it is the definition's text again). */
  function setText(ref, text, base) {
    const d = draftOf(ref);
    if (d) { d.text = text; persist(); return; }
    const had = buffers.has(ref);
    if (text === base) buffers.delete(ref); else buffers.set(ref, { text, base });
    if (had !== buffers.has(ref)) { decorate(document); if (current && current.ref === ref && current.controls) current.controls(); }
  }
  /** A change made in the form: the text parsed, fn(document) applied, written back with the text's indentation. */
  function edit(ref, base, fn) {
    const text = textOf(ref, base === null ? null : { text: base }), p = parse(text);
    if (!p.doc) return;
    fn(p.doc);
    setText(ref, JSON.stringify(p.doc, null, indentOf(text)) + '\n', base);
  }

  /** The marks after names (tree.js's mark): "not kept yet" where something typed is not kept, else "unsaved" or "removed". */
  function decorate(root) {
    for (const s of (root || document).querySelectorAll('.umark[data-ref]')) {
      const typed = buffers.has(s.dataset.ref) || s.dataset.draft === '1';
      const text = typed ? 'not kept yet' : s.dataset.removed === '1' ? 'removed' : s.dataset.unsaved === '1' ? 'unsaved' : '';
      if (s.textContent !== text) s.textContent = text;   // a mark already right is not touched (spec-w4 R2)
      s.classList.toggle('typed', typed);
    }
  }

  // ---- Selections -------------------------------------------------------------------
  const prefixes = ['edit:', 'branch:'];
  /** The reference a selection is about: 'edit:<ref>' and 'branch:<ref>' are about <ref>. */
  function subject(sel) { for (const p of prefixes) if (sel && sel.startsWith(p)) return sel.slice(p.length); return sel; }
  /** Whether a selection is this module's drawer: the editor, the branch form or a draft, for a session that may edit. */
  function owns(sel, data) { return !!sel && A.may('edit') && (prefixes.some(p => sel.startsWith(p)) || !!draftOf(sel)); }
  function drawer(aside, sel, act, data, screen) {
    if (sel.startsWith('branch:')) return branchForm(aside, sel, sel.slice(7), act, data);
    return editor(aside, sel, subject(sel), act, data, screen);
  }
  /** Puts node in the drawer in one step (screens.js's putInPlace: the focused control by data-key, its caret and the scroll given back); else the heading takes the focus when the focus was in the drawer or nowhere. */
  function swapInto(aside, node) {
    const active = document.activeElement, nowhere = !active || active === document.body;
    const r = S.parts.putInPlace(aside, node, aside.parentElement);
    if (!r.found && (r.inside || nowhere)) { const t = aside.querySelector('h2'); if (t && aside.closest('.drawer.open')) t.focus({ preventScroll: true }); }
  }

  // ---- The editor ---------------------------------------------------------------------
  // A reading on the timer or on focus never touches the editor or the branch form (spec-w4 R3): what is typed stays.
  // After a control's answer (aside._again 'control') they are drawn again in place.
  function editor(aside, sel, ref, act, data, screen) {
    const key = 'editor:' + sel;
    if (aside._for === key && aside._again !== 'control') return true;
    aside._for = key;
    const draft = draftOf(ref);
    if (!(aside._editing === ref && aside.querySelector('.editor'))) { aside.textContent = ''; aside.appendChild(h('p', 'note', 'Reading…')); }
    aside._editing = ref;
    Promise.all([draft ? null : P.read('definition', { reference: ref }), P.read('definitions')]).then(([def, all]) => {
      if (aside._for !== key) return;
      const here = { aside, key, ref, controls: null };
      current = here;
      const rebuild = () => { if (aside._for === key) { aside._for = null; editor(aside, sel, ref, act, data, screen); } };
      here.rebuild = rebuild;
      swapInto(aside, editorView(here, ref, draft ? null : def, all.definitions, act, data, screen, sel));
    }, error => { if (aside._for !== key) return; aside._editing = null; aside.textContent = ''; aside.appendChild(A.refusal(error)); });
    return true;
  }
  function editorView(here, ref, def, all, act, data, screen, sel) {
    const draft = draftOf(ref), kind = def ? def.kind : 'recipe', base = def ? def.text : null, text = textOf(ref, def), p = parse(text);
    const doc = p.doc || (def && def.document) || {};
    const view = kind === 'recipe' && p.doc ? (views.get(ref) || 'form') : 'text';
    const ins = h('div', 'inspector editor'); ins.dataset.ref = ref;
    // The header: what it is, its state, and its marks.
    const hd = h('header'), parent = draft ? data.map.byId.get(draft.parent) : null;
    hd.appendChild(h('span', 'kicker', draft ? 'draft · from ' + (parent ? Tree.nameOf(parent) : draft.parent) : (kind === 'recipe' ? 'editing · ' : 'editing ' + kind + ' · ') + ref));
    const t = h('h2', null, (typeof doc.title === 'string' && doc.title) || (def && def.title) || ref); t.tabIndex = -1; hd.appendChild(t);
    const meta = h('div', 'ins-meta');
    if (draft) meta.appendChild(h('span', 'chip ' + (P.KINDS.some(k => k.id === doc.change) ? doc.change : P.UNSET) + ' draft', 'draft'));
    else meta.appendChild(modelState(def.state));
    const mark = Tree.mark({ id: ref, unsaved: !!(def && def.unsaved), draft: !!draft }); if (def && def.removed) mark.dataset.removed = '1'; meta.appendChild(mark);
    hd.appendChild(meta); ins.appendChild(hd);
    // Back to what it was opened from.
    const back = h('div', 'actions');
    if (draft) { if (parent) back.appendChild(button('btn sm ghost', 'From ' + Tree.refName(parent), 'editor:' + ref + ':parent', () => act.go('map', parent.id))); }
    else if (screen === 'map' && data.map.byId.has(ref)) back.appendChild(button('btn sm ghost', '← The model', 'editor:' + ref + ':back', () => act.select(ref)));
    else if (screen === 'data') back.appendChild(button('btn sm ghost', '← The dataset', 'editor:' + ref + ':back', () => act.select(ref)));
    if (back.children.length) ins.appendChild(back);
    if (picking && picking.reference === ref) ins.appendChild(pickingBanner(act));
    // The two views of the one text.
    const seg = h('div', 'seg'); seg.setAttribute('role', 'group'); seg.setAttribute('aria-label', 'View');
    if (kind === 'recipe' && p.doc) for (const [v, label] of [['form', 'Form'], ['text', 'Text']]) {
      const b = button(null, label, 'editor:' + ref + ':view-' + v, () => { views.set(ref, v); here.rebuild(); }); b.setAttribute('aria-pressed', String(view === v)); seg.appendChild(b);
    }
    if (seg.children.length) ins.appendChild(seg);
    if (kind === 'recipe' && !p.doc) ins.appendChild(h('p', 'failure', 'The text is not valid JSON, so the form cannot show it: ' + p.error + ' Correct it in the text below.'));
    // A draft opens with what keeping it would find, and with where its settings came from.
    if (draft && draft.problems.length) ins.appendChild(problemList(draft.problems, 'When it was drafted, keeping it would have found:'));
    if (draft && draft.inlined) ins.appendChild(h('p', 'note', 'The settings were copied from ' + draft.inlined + ' so that they can be changed here; that file is not changed.'));
    ins.appendChild(view === 'form' ? recipeForm(ref, base, p.doc, all, data, act, sel) : textView(ref, base, text));
    if (draft) ins.appendChild(stepsBlock(ref, { kept: false }, act, data, null));
    else {
      // Keep, Discard edit, Remove and Save; drawn again when typing starts or ends (Discard edit then applies).
      const box = h('div');
      const controls = () => {
        const typed = buffers.has(ref), edited = def.unsaved || def.removed;
        box.textContent = '';
        box.appendChild(A.group('edit:' + ref, [
          { id: 'keep', label: 'Keep', cls: 'btn primary', who: 'edit', op: 'set_definition', busy: 'Keeping…', args: () => ({ reference: ref, text: textOf(ref, def) }), done: () => buffers.delete(ref) },
          { id: 'discard', label: 'Discard edit', cls: 'btn', who: 'edit', busy: 'Discarding…', hidden: !typed && !edited,
            confirm: (typed && edited ? 'Drop what was typed here, and put back' : typed ? 'Drop what was typed here; the definition stays as it is kept.' : 'Put back') + (edited ? ' the file in the project folder in place of the unsaved ' + (def.removed ? 'removal' : 'edit') + '; a definition the folder has no file for is dropped.' : ''),
            // Whether there is an unsaved edit to put back is read afresh: this drawer may have been drawn before a Keep.
            run: async () => {
              buffers.delete(ref); decorate(document);
              const now = await P.call('definition', { reference: ref });
              return now.unsaved || now.removed ? P.call('revert_definition', { reference: ref }) : { reference: ref, dropped: false };
            },
            done: r => { if (r && r.dropped) act.select(null); } },
          { id: 'remove', label: 'Remove', cls: 'btn ghost', who: 'edit', op: 'remove_definition', busy: 'Removing…', hidden: !!def.removed, args: () => ({ reference: ref }),
            confirm: 'Remove ' + ref + ': it is marked removed and its file is deleted when the project is saved; one never saved is dropped now.',
            done: () => { buffers.delete(ref); act.select(null); } },
          { id: 'save', label: 'Save', cls: 'btn', who: 'edit', op: 'save', busy: 'Saving…', hidden: !edited }
        ]));
        box.appendChild(h('p', 'note', 'Keep checks the text and keeps it in Tuldok as an unsaved edit; Save writes every unsaved edit to the project folder.'));
      };
      here.controls = controls; controls(); ins.appendChild(box);
    }
    decorate(ins);
    return ins;
  }
  function textView(ref, base, text) {
    const l = h('label', 'code-field');
    l.appendChild(h('span', 'small muted', 'The definition, as JSON'));
    const area = h('textarea', 'code'); area.value = text; area.spellcheck = false; area.autocomplete = 'off'; area.wrap = 'off';
    area.rows = Math.min(28, Math.max(10, text.split('\n').length + 1)); area.dataset.key = 'editor:' + ref + ':text';
    area.addEventListener('input', () => setText(ref, area.value, base));
    l.appendChild(area);
    return l;
  }
  function problemList(problems, lead) {
    const errors = problems.some(p => p.severity !== 'warning');
    const box = h('div', errors ? 'failure refusal problems' : 'problems warnings');
    box.appendChild(h('p', null, lead));
    const ul = h('ul');
    for (const p of problems) { const where = [p.path, p.pointer].filter(x => x && x !== '/').join(' '); ul.appendChild(h('li', null, (p.severity === 'warning' ? 'Warning: ' : '') + (where ? where + ': ' : '') + (p.message || ''))); }
    box.appendChild(ul);
    box.appendChild(h('p', 'small', 'Keep checks the text again and lists what is still wrong.'));
    return box;
  }

  // ---- The form of a recipe ---------------------------------------------------------------
  function recipeForm(ref, base, doc, all, data, act, sel) {
    const f = h('div', 'form editor-form'), k = name => 'editor:' + ref + ':' + name, upd = fn => edit(ref, base, fn);
    const field = (label, control, hint) => { const l = h('label'); l.appendChild(document.createTextNode(label)); l.appendChild(control); if (hint) l.appendChild(h('span', 'hint', hint)); return l; };
    const input = (type, value, name, max) => { const i = h('input'); i.type = type; if (value !== undefined && value !== null) i.value = String(value); if (max) i.maxLength = max; i.dataset.key = k(name); i.autocomplete = 'off'; if (type === 'text') i.spellcheck = false; return i; };
    const choose = (options, value, name, label) => { const s = h('select'); s.dataset.key = k(name); s.setAttribute('aria-label', label); for (const [v, t] of options) { const o = h('option', null, t); o.value = v; o.selected = v === value; s.appendChild(o); } return s; };
    const asNumber = text => { const t = text.trim(); if (!t) return null; const n = Number(t); return Number.isFinite(n) ? n : undefined; };
    // A draft's node on the map follows its title, group and kind when such a field is left.
    const isDraftRef = !!draftOf(ref), redraw = () => { if (isDraftRef) { publish(); act.redraw(); } };

    const title = input('text', doc.title, 'title', 200); title.required = true;
    title.addEventListener('input', () => upd(d => { d.title = title.value; })); title.addEventListener('change', redraw);
    f.appendChild(field('Title', title));
    const two = h('div', 'two');
    const short = input('text', isObject(doc.labels) && typeof doc.labels.short === 'string' ? doc.labels.short : '', 'short', 16);
    short.addEventListener('input', () => upd(d => {
      if (short.value) { if (!isObject(d.labels)) d.labels = {}; d.labels.short = short.value; }
      else if (isObject(d.labels)) { delete d.labels.short; if (!Object.keys(d.labels).length) delete d.labels; }
    }));
    short.addEventListener('change', redraw);
    two.appendChild(field('Short label', short, 'at most 16 characters'));
    const groups = (data.map.groups || []).map(g => { const up = []; let at = g; const byId = new Map(data.map.groups.map(x => [x.id, x])); while (at.parent && byId.has(at.parent) && up.length < 8) { at = byId.get(at.parent); up.unshift(at.title); } return [g.id, up.concat([g.title]).join(' / ')]; });
    const groupValue = typeof doc.group === 'string' ? doc.group : '';
    if (groupValue && !groups.some(g => g[0] === groupValue)) groups.push([groupValue, groupValue + ' (not a group of the project)']);
    const grp = choose([['', 'None']].concat(groups), groupValue, 'group', 'Group');
    grp.addEventListener('change', () => { upd(d => { if (grp.value) d.group = grp.value; else delete d.group; }); redraw(); });
    two.appendChild(field('Group', grp));
    f.appendChild(two);
    // Kind of change: the four kinds, or not set.
    const kinds = h('div', 'radio'); kinds.setAttribute('role', 'radiogroup'); kinds.setAttribute('aria-label', 'Kind of change');
    const changeValue = P.KINDS.some(x => x.id === doc.change) ? doc.change : '';
    for (const [v, label] of P.KINDS.map(x => [x.id, x.label]).concat([['', 'Not set']])) {
      const l = h('label', 'chip-radio'); const r = h('input'); r.type = 'radio'; r.name = 'change-' + ref; r.value = v; r.checked = v === changeValue; r.dataset.key = k('change-' + (v || 'unset'));
      r.addEventListener('change', () => { if (!r.checked) return; upd(d => { if (v) d.change = v; else delete d.change; }); redraw(); });
      l.appendChild(r); l.appendChild(h('span', 'chip ' + (v || P.UNSET), label)); kinds.appendChild(l);
    }
    f.appendChild(field('Kind of change', kinds));
    // Derived from: the parent's name, Pick on the map, Clear.
    const parentRef = typeof doc.derived_from === 'string' ? doc.derived_from : null, pm = parentRef && data.map.byId.get(parentRef);
    const der = h('div', 'derived');
    der.appendChild(h('span', 'derived-name' + (parentRef ? '' : ' faint'), parentRef ? (pm ? Tree.nameOf(pm) : parentRef) : 'none'));
    der.appendChild(button('btn sm', 'Pick on the map', k('pick'), () => startPicking(ref, base, sel, act)));
    if (parentRef) der.appendChild(button('btn sm ghost', 'Clear', k('clear'), () => { upd(d => { delete d.derived_from; }); if (current && current.rebuild) current.rebuild(); }));
    f.appendChild(field('Derived from', der));
    const desc = h('textarea'); desc.rows = 3; desc.maxLength = 4000; desc.value = typeof doc.description === 'string' ? doc.description : ''; desc.dataset.key = k('description');
    desc.addEventListener('input', () => upd(d => { if (desc.value) d.description = desc.value; else delete d.description; }));
    f.appendChild(field('What this model changes', desc, 'at most 4,000 characters'));
    if (!isObject(doc.run)) { f.appendChild(h('p', 'note', 'This recipe has no run: it is earlier work, or its run is to be written in the text view.')); return f; }
    const run = doc.run, defs = all.filter(d => !d.removed), env = typeof run.environment === 'string' ? run.environment : '';
    const envs = defs.filter(d => d.kind === 'environment').map(d => [d.reference, d.title + ' · ' + d.reference]);
    if (env && !envs.some(e => e[0] === env)) envs.push([env, env + ' (not an environment of the project)']);
    const es = choose((env ? [] : [['', 'None']]).concat(envs), env, 'environment', 'Environment');
    es.addEventListener('change', () => upd(d => { if (!isObject(d.run)) return; if (es.value) d.run.environment = es.value; else delete d.run.environment; }));
    f.appendChild(field('Environment', es));
    // Each input from a dataset: another dataset, keeping a named output.
    const sets = defs.filter(d => d.kind === 'dataset').map(d => [d.reference, d.title + ' · ' + d.reference]);
    for (const [name, v] of Object.entries(isObject(run.inputs) ? run.inputs : {})) {
      const from = typeof v === 'string' ? v : isObject(v) && typeof v.from === 'string' ? v.from : null;
      if (!from || !from.startsWith('datasets/')) continue;
      const options = sets.some(s => s[0] === from) ? sets : sets.concat([[from, from]]);
      const s = choose(options, from, 'input-' + name, 'Input ' + name);
      s.addEventListener('change', () => upd(d => { const ins = isObject(d.run) && isObject(d.run.inputs) ? d.run.inputs : null; if (!ins) return; if (isObject(ins[name])) ins[name].from = s.value; else ins[name] = s.value; }));
      f.appendChild(field('Input ' + name + (isObject(v) && v.output ? ' · its output ' + v.output : ''), s));
    }
    // Settings: one field per top-level number, text or true/false; the rest are edited in the text.
    const st = h('div', 'settings'); st.appendChild(h('h3', null, 'Settings'));
    if (isObject(run.settings)) {
      const grid = h('div', 'two'), rest = [];
      for (const [name, v] of Object.entries(run.settings)) {
        const set = fn => upd(d => { if (isObject(d.run) && isObject(d.run.settings)) fn(d.run.settings); });
        if (typeof v === 'number') {
          const i = input('number', v, 'setting-' + name); i.step = 'any';
          i.addEventListener('input', () => { const n = asNumber(i.value); if (n === null || n === undefined) return; set(s => { s[name] = n; }); });
          grid.appendChild(field(name, i));
        } else if (typeof v === 'string') {
          const i = input('text', v, 'setting-' + name); i.addEventListener('input', () => set(s => { s[name] = i.value; })); grid.appendChild(field(name, i));
        } else if (typeof v === 'boolean') {
          const l = h('label', 'check'); const c = h('input'); c.type = 'checkbox'; c.checked = v; c.dataset.key = k('setting-' + name);
          c.addEventListener('change', () => set(s => { s[name] = c.checked; })); l.appendChild(c); l.appendChild(document.createTextNode(' ' + name)); grid.appendChild(l);
        } else rest.push(name);
      }
      if (grid.children.length) st.appendChild(grid); else st.appendChild(h('p', 'note', 'No setting is a number, a text or true/false.'));
      if (rest.length) st.appendChild(h('p', 'note', 'Edited in the text: ' + rest.join(', ') + '.'));
    } else if (typeof run.settings_file === 'string') {
      st.appendChild(h('p', 'note mono', run.settings_file));
      st.appendChild(h('p', 'note', 'Its settings are in this file, which is changed in the code. A branch of this model carries its own copy of them, which its form can change.'));
    } else st.appendChild(h('p', 'note', 'It has no settings.'));
    f.appendChild(st);
    // Resources.
    const rs = h('div', 'settings'); rs.appendChild(h('h3', null, 'Resources'));
    const res = isObject(run.resources) ? run.resources : {};
    const setRes = fn => upd(d => { if (!isObject(d.run)) return; if (!isObject(d.run.resources)) d.run.resources = {}; fn(d.run.resources); if (!Object.keys(d.run.resources).length) delete d.run.resources; });
    const gl = h('label', 'check'); const gpu = h('input'); gpu.type = 'checkbox'; gpu.checked = res.gpu === true; gpu.dataset.key = k('gpu');
    gpu.addEventListener('change', () => setRes(r => { if (gpu.checked) r.gpu = true; else if ('gpu' in r) r.gpu = false; }));
    gl.appendChild(gpu); gl.appendChild(document.createTextNode(' Uses the GPU')); rs.appendChild(gl);
    const rg = h('div', 'two');
    for (const [name, label] of [['wall_hours', 'Wall hours'], ['disk_gb', 'Disk (GB)']]) {
      const i = input('number', typeof res[name] === 'number' ? res[name] : '', name); i.step = 'any'; i.min = '0';
      i.addEventListener('input', () => { const n = asNumber(i.value); if (n === undefined) return; setRes(r => { if (n === null) delete r[name]; else r[name] = n; }); });
      rg.appendChild(field(label, i, 'empty: not stated'));
    }
    rs.appendChild(rg); f.appendChild(rs);
    return f;
  }

  // ---- Pick on the map --------------------------------------------------------------------
  function startPicking(ref, base, sel, act) {
    picking = { reference: ref, base, sel: draftOf(ref) ? ref : 'edit:' + ref }; pickNote = '';
    if (location.hash.startsWith('#map/')) act.reopen(); else act.go('map', picking.sel);
    setTimeout(() => A.focusKey('editor:' + ref + ':stop-picking'), 0);
  }
  function pickingBanner(act) {
    const box = h('div', 'picking'); box.setAttribute('role', 'status');
    box.appendChild(h('p', null, 'Press a model on the map to make it the parent · Escape to stop'));
    if (pickNote) box.appendChild(h('p', 'small warnline', pickNote));
    box.appendChild(button('btn sm', 'Stop', 'editor:' + picking.reference + ':stop-picking', () => { stopPicking(act); }));
    return box;
  }
  function stopPicking(act) { const was = picking; picking = null; pickNote = ''; act.reopen(); if (was) setTimeout(() => A.focusKey('editor:' + was.reference + ':pick'), 0); }
  /** screens.js, when a model is pressed on the map: true when it was taken as the parent being picked. */
  function picked(id, act) {
    if (!picking) return false;
    if (id === picking.reference) { pickNote = 'A model is not derived from itself: press another one.'; act.reopen(); return true; }
    if (draftOf(id)) { pickNote = 'A draft cannot be a parent before it is kept: press another one.'; act.reopen(); return true; }
    const { reference, base, sel } = picking; picking = null; pickNote = '';
    edit(reference, base, d => { d.derived_from = id; });
    if (draftOf(reference)) publish();
    act.go('map', sel); act.reopen();
    setTimeout(() => A.focusKey('editor:' + reference + ':pick'), 0);
    return true;
  }
  /** app.js, on Escape: leaves the picking state; true when it was in it. */
  function escape() { if (!picking) return false; const was = picking; picking = null; pickNote = ''; if (current) current.rebuild && current.rebuild(); setTimeout(() => A.focusKey('editor:' + was.reference + ':pick'), 0); return true; }

  // ---- Branch from here -------------------------------------------------------------------
  function branchForm(aside, sel, parentRef, act, data) {
    if (aside._for === sel && aside._again !== 'control') return true;
    aside._for = sel; aside._editing = null;
    const m = data.map.byId.get(parentRef);
    const ins = h('div', 'inspector branch');
    if (!m || m.draft) { ins.appendChild(h('p', 'empty', 'There is no model ' + parentRef + ' on the map to branch from.')); swapInto(aside, ins); return true; }
    const key = 'branch:' + parentRef, s = A.slot(key);
    if (s.text.change === undefined) s.text.change = m.kind === P.UNSET ? '' : m.kind;
    const hd = h('header'); hd.appendChild(h('span', 'kicker', 'branch · from ' + Tree.nameOf(m)));
    const t = h('h2', null, 'A new model from ' + Tree.refName(m)); t.tabIndex = -1; hd.appendChild(t); ins.appendChild(hd);
    ins.appendChild(h('p', 'note', 'A new recipe written from this one, with its model, group, run and settings, derived from it. It is a draft in this page until it is kept.'));
    const f = h('div', 'form');
    const field = (label, control, hint) => { const l = h('label'); l.appendChild(document.createTextNode(label)); l.appendChild(control); if (hint) l.appendChild(h('span', 'hint', hint)); return l; };
    const title = h('input'); title.type = 'text'; title.maxLength = 200; title.required = true; title.value = s.text.title || ''; title.dataset.key = key + ':field:title'; title.autocomplete = 'off';
    title.placeholder = 'What the new model is';
    title.addEventListener('input', () => {
      s.text.title = title.value;
      // A refusal for a missing title is over once one is typed.
      if (s.refusal && title.value.trim() && /title/.test(s.refusal.error.message)) { s.refusal = null; const r = ins.querySelector('.act-group .refusal'); if (r) r.remove(); }
    });
    title.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); A.focusKey(key + ':create'); const b = ins.querySelector('[data-key="' + CSS.escape(key + ':create') + '"]'); if (b && !b.disabled) b.click(); } });
    f.appendChild(field('Title (required)', title, 'at most 200 characters'));
    const kinds = h('div', 'radio'); kinds.setAttribute('role', 'radiogroup'); kinds.setAttribute('aria-label', 'Kind of change');
    for (const [v, label] of P.KINDS.map(x => [x.id, x.label]).concat([['', 'Not set']])) {
      const l = h('label', 'chip-radio'); const r = h('input'); r.type = 'radio'; r.name = key + ':change'; r.value = v; r.checked = (s.text.change || '') === v; r.dataset.key = key + ':change-' + (v || 'unset');
      r.addEventListener('change', () => { if (r.checked) s.text.change = v; });
      l.appendChild(r); l.appendChild(h('span', 'chip ' + (v || P.UNSET), label)); kinds.appendChild(l);
    }
    f.appendChild(field('Kind of change', kinds, m.kind === P.UNSET ? 'its parent names none' : 'its parent\'s to begin with'));
    const desc = h('textarea'); desc.rows = 3; desc.maxLength = 4000; desc.value = s.text.description || ''; desc.dataset.key = key + ':field:description';
    desc.addEventListener('input', () => { s.text.description = desc.value; });
    f.appendChild(field('What the model changes', desc, 'at most 4,000 characters'));
    ins.appendChild(f);
    ins.appendChild(A.group(key, [
      { id: 'create', label: 'Create', cls: 'btn primary', who: 'edit', busy: 'Creating…', local: true,
        run: async st => {
          const wanted = (st.text.title || '').trim();
          if (!wanted) throw Error('A branch needs a title.');
          const args = { recipe: parentRef, title: wanted.slice(0, 200) };
          if (st.text.change) args.change = st.text.change;
          const about = (st.text.description || '').trim(); if (about) args.description = about.slice(0, 4000);
          let answer = await P.call('draft_branch', args);
          // A draft of this page holds the name already: the next free one.
          const stem = answer.reference.slice('recipes/'.length).replace(/-\d+$/, '').slice(0, 110);
          for (let n = 2; draftOf(answer.reference) && n < 200; n++) {
            if (draftOf('recipes/' + stem + '-' + n)) continue;
            try { answer = await P.call('draft_branch', Object.assign({}, args, { name: stem + '-' + n })); } catch (error) { if (error.code !== 'invalid') throw error; }
          }
          if (draftOf(answer.reference)) throw Error('No free name was found for the branch; give it another title.');
          return answer;
        },
        done: answer => {
          drafts.push({ reference: answer.reference, parent: parentRef, text: answer.text, inlined: answer.inlined || null, problems: answer.problems || [] });
          views.set(answer.reference, 'form'); persist(); publish();
          act.redraw().then(() => act.go('map', answer.reference));
        } },
      { id: 'back', label: 'Back', cls: 'btn ghost', onClick: () => act.go('map', parentRef) }
    ]));
    swapInto(aside, ins);
    return true;
  }

  // ---- The steps of a new model ----------------------------------------------------------------
  /** Whether a model's drawer shows the steps of a new model: a draft, one branched here, or one never built (unless it is earlier work). */
  const followsSteps = m => !!m && (m.draft || m.planned || followed.includes(m.id));
  /**
   * The steps of a model of the map (screens.js): read its definition, runs and
   * the build requests; earlier work gets planGroup() instead (as phase 2).
   * Fills box, on the page or not yet (a drawer read again is built off the
   * page), and resolves once it is filled.
   */
  function steps(box, m, act, data, planGroup) {
    return Promise.all([P.read('definition', { reference: m.id }), P.read('runs', { reference: m.id }), P.read('build_requests')]).then(([def, runs, requests]) => {
      box.textContent = '';
      if (isObject(def.document) && def.document.earlier_work && !followed.includes(m.id)) { if (['not-built', 'out-of-date', 'failed'].includes(m.state)) box.appendChild(planGroup()); return; }
      const asked = requests.requests.filter(r => (r.targets || []).includes(m.id) && !['declined', 'cancelled', 'expired'].includes(r.state));
      const runList = runs.runs, started = runList.filter(r => r.started_at || ['running', 'succeeded', 'failed'].includes(r.state));
      box.appendChild(stepsBlock(m.id, {
        kept: true, saved: !def.unsaved, requested: asked.length > 0 || runList.length > 0, running: started.length > 0,
        runningNow: runList.some(r => r.state === 'running'), built: ['built', 'out-of-date'].includes(m.state), unsaved: def.unsaved,
        request: asked[0] || null, run: runList[0] || null, state: m.state
      }, act, data, planGroup));
    }, error => { box.textContent = ''; box.appendChild(A.refusal(error)); });
  }
  function stepsBlock(ref, f, act, data) {
    const wrap = h('div', 'new-steps');
    wrap.appendChild(h('h3', null, 'From draft to built'));
    const ol = h('ol', 'steps');
    const rows = [
      ['Kept', f.kept, f.kept ? 'Kept in Tuldok as a definition.' : 'Not kept yet: it is in this page only, and Keep checks it.'],
      ['Saved', f.saved, f.saved ? 'Written to the project folder.' : f.kept ? 'An unsaved edit: Save writes it to the project folder.' : 'Not in the project folder.'],
      ['Build requested', f.requested, f.request ? 'Asked for' + (f.request.state === 'awaiting-approval' ? ', awaiting approval.' : ' · ' + f.request.state + '.') : f.requested ? 'Asked for.' : 'Not asked for: plan its build first.'],
      ['Running', f.running, f.runningNow ? 'Running now.' : f.running ? 'Its build has run' + (f.run ? ' · ' + f.run.state : '') + '.' : 'Not started.'],
      ['Built', f.built, f.built ? 'Built: its product is on this machine.' : 'No product yet.']
    ];
    let next = false;
    for (const [title, done, sub] of rows) {
      const now = !done && !next; if (now) next = true;
      const li = h('li', done ? 'done' : 'todo'); li.dataset.step = title;
      li.appendChild(S.stateEl(done ? 'good' : now && (title === 'Running' && f.runningNow) ? 'pending' : 'neutral', ''));
      const t = h('span'); t.appendChild(h('span', 'title', title)); t.appendChild(h('span', 'sub', sub)); li.appendChild(t); ol.appendChild(li);
    }
    wrap.appendChild(ol);
    // One primary button, the next step; and Discard.
    const items = [];
    if (!f.kept) {
      items.push({ id: 'keep', label: 'Keep', cls: 'btn primary', who: 'edit', op: 'set_definition', busy: 'Keeping…', args: () => ({ reference: ref, text: textOf(ref, null) }),
        done: () => { drafts = drafts.filter(d => d.reference !== ref); if (!followed.includes(ref)) followed.push(ref); persist(); publish(); } });
      items.push({ id: 'discard', label: 'Discard', cls: 'btn ghost', who: 'edit', local: true, confirm: 'Drop this draft; nothing of it was kept.', run: async () => true,
        done: () => { const d = draftOf(ref); drafts = drafts.filter(x => x.reference !== ref); persist(); publish(); act.redraw().then(() => act.go('map', d ? d.parent : undefined)); } });
    } else {
      if (!f.saved) items.push({ id: 'save', label: 'Save', cls: 'btn primary', who: 'edit', op: 'save', busy: 'Saving…' });
      else if (!f.requested) items.push({ id: 'plan', label: 'Plan build', cls: 'btn primary', who: 'request', onClick: () => act.select('plan:' + ref) });
      else items.push({ id: 'train', label: 'Open in Train', cls: 'btn primary', onClick: () => act.go('train', f.request && !f.run ? 'request:' + f.request.id : f.run ? 'run:' + f.run.id : undefined) });
      if (f.unsaved) items.push({ id: 'discard', label: 'Discard', cls: 'btn ghost', who: 'edit', op: 'revert_definition', busy: 'Discarding…', args: () => ({ reference: ref }),
        confirm: 'Put back the file in the project folder in place of the unsaved edit; a model never saved is dropped.', done: r => { if (r && r.dropped) act.select(null); } });
    }
    wrap.appendChild(A.group(f.kept ? 'model:' + ref : 'draft:' + ref, items));
    return wrap;
  }

  // ---- The Overview's list of every definition ----------------------------------------------------
  function definitionList(box, defs, sel, act) {
    const can = A.may('edit');
    box.appendChild(sect('Every definition', defs.length + (can ? ' · each opens the editor' : '')));
    if (!defs.length) { box.appendChild(h('p', 'empty', 'The project has no definitions.')); return; }
    const kinds = KIND_ORDER.concat([...new Set(defs.map(d => d.kind))].filter(k => !KIND_ORDER.includes(k)));
    for (const kind of kinds) {
      const mine = defs.filter(d => d.kind === kind); if (!mine.length) continue;
      box.appendChild(h('h3', 'ov-kind', (KIND_TITLE[kind] || kind) + ' · ' + mine.length));
      const ul = h('ul', 'rows defs');
      for (const d of mine) {
        const li = h('li'), row = can ? button('row def', null, 'open-edit:' + d.reference, () => act.select(sel === 'edit:' + d.reference ? null : 'edit:' + d.reference)) : h('div', 'row def');
        if (can) row.setAttribute('aria-pressed', String(sel === 'edit:' + d.reference));
        row.dataset.ref = d.reference;
        row.appendChild(h('span', 'mono name', d.reference.slice(d.reference.indexOf('/') + 1)));
        row.appendChild(h('span', 'title', d.title));
        row.appendChild(modelState(d.state));
        const mark = Tree.mark({ id: d.reference, unsaved: d.unsaved }); if (d.removed) mark.dataset.removed = '1'; row.appendChild(mark);
        li.appendChild(row); ul.appendChild(li);
      }
      box.appendChild(ul);
    }
  }

  return { load, subject, owns, drawer, isDraft, picked, escape, decorate, followsSteps, steps, definitionList };
})();
