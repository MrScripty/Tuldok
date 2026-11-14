'use strict';
// The Pumas endpoint on the page (docs/plans/definition-first-projects/spec-d5.md section 5): the endpoint on the Train
// tab, beside the environments (its address, whether it answers, its version and the models it serves with what each
// takes and makes; for the owner, Set, Clear and Find on this machine in its drawer), and the Data tab's Generate form,
// which keeps a new dataset whose run is the step generate as an unsaved edit, as Import and Freeze do (annotate.js).
// Everything offered comes from the answer of `endpoint` at that moment: what to make is only what some served model
// makes, a model only one that makes it, an option only one its capability declares, with the advertised bounds as the
// field's minimum and maximum. Building the dataset is the existing plan and request. Suggest on the Annotate tab is
// annotate.js's.
//
// Updating in place (spec-w4): the endpoint's answer is not watched; it is read with the Train tab and forgotten, as
// every answer not watched, when a reading finds something changed (or after a control's answer), so the section is
// drawn again in place only then. Its drawer is drawn again in place the same way, its typed address kept in its
// group's slot (actions.js). The Generate form is a drawer form like Import and Freeze: never touched by a reading on
// the timer or on focus, its text kept in its group's slot.
window.LabGenerate = (() => {
  const P = window.TuldokProject, S = window.LabScreens, A = window.LabActions, h = window.LabCharts.h;
  const { sect, putInPlace, block } = S.parts;
  const FORMAT = 'tuldok_definition_v1';
  const MAKE_WORD = { text: 'Texts', image: 'Images (PNG)' };
  const REQUIRED = { image: ['width', 'height'] };   // the options a generate of this kind cannot do without (docs/contracts/project-folder.md)
  const button = (cls, text, key, onClick) => { const b = h('button', cls, text); b.type = 'button'; if (key) b.dataset.key = key; if (onClick) b.addEventListener('click', onClick); return b; };
  const num = v => Number.isInteger(v) ? v.toLocaleString('en-GB') : String(v);
  const bound = b => num(b.minimum) + ' to ' + num(b.maximum);
  const listed = xs => xs.length < 2 ? xs.join('') : xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1];
  const entryKey = m => m.model + '\u0000' + m.profile;
  // The options of a capability in the order the contract names them (the server's answer holds them in key order).
  const ORDER = ['max_tokens', 'temperature', 'top_p', 'width', 'height'];
  const rank = n => { const i = ORDER.indexOf(n); return i < 0 ? ORDER.length : i; };
  const optionsOf = made => Object.entries(made.options).sort(([a], [b]) => rank(a) - rank(b) || (a < b ? -1 : a > b ? 1 : 0));
  const forms = () => window.LabAnnotate.forms;

  // ---- What the endpoint answer says, in words -------------------------------------------------------------------
  /** {tone, word, line}: the endpoint's state in one mark and one sentence. */
  function standing(ep) {
    if (ep.error) return { tone: 'serious', word: 'not read', line: ep.error.message };
    if (!ep.address) return { tone: 'warn', word: 'not set', line: 'No Pumas endpoint is set on this machine, so nothing can be generated or suggested here.' };
    if (!ep.answered) return { tone: 'serious', word: 'does not answer', line: ep.problem || 'It did not answer.' };
    return { tone: 'good', word: 'answers', line: (ep.version ? 'Pumas ' + ep.version : 'Version not reported') + ' · ' + ep.models.length + (ep.models.length === 1 ? ' model' : ' models') + ' served' };
  }
  /** The (model, profile) entries that can make a dataset now, by what they make. */
  function makers(ep) {
    const by = {};
    if (ep && !ep.error && ep.answered) for (const m of ep.models) for (const made of m.makes) (by[made.make] = by[made.make] || []).push({ m, made });
    return by;
  }
  /** Whether the profile has to be written: the endpoint says so, or it serves the model with more than one. */
  const needsProfile = (ep, m) => m.profile_required || ep.models.filter(x => x.model === m.model).length > 1;

  // ---- Train: the endpoint beside the environments ------------------------------------------------------------------
  /** The section of the Train tab: a row opening the endpoint's drawer, and the models it serves. */
  function section(frag, ep, sel, act) {
    const st = standing(ep);
    const head = sect('Pumas endpoint', 'a setting of this machine'); head.classList.add('gap');
    head.appendChild(h('span', 'spacer'));
    head.appendChild(A.group('train:endpoint', [{ id: 'open', label: ep.address ? 'Change' : 'Set the endpoint', cls: 'btn sm', who: 'owner', onClick: () => act.select(sel === 'endpoint' ? null : 'endpoint') }], { inline: true }));
    frag.appendChild(head);
    const ul = h('ul', 'rows'), li = h('li'), r = button('row env ep-row', null, 'open-endpoint', () => act.select(sel === 'endpoint' ? null : 'endpoint'));
    r.setAttribute('aria-pressed', String(sel === 'endpoint'));
    r.appendChild(S.stateEl(st.tone, st.word));
    const t = h('span'); t.appendChild(h('span', 'title', ep.address || 'No endpoint set')); t.appendChild(h('span', 'sub' + (st.tone === 'serious' ? ' warnline' : ''), st.line)); r.appendChild(t);
    r.appendChild(h('span', 'sub', ep.address ? 'generation and suggestions go here' : A.may('owner') ? 'set it to generate and suggest' : 'the owner sets it'));
    li.appendChild(r); ul.appendChild(li); frag.appendChild(ul);
    if (ep.error || !ep.answered) return;
    if (!ep.models.length) { frag.appendChild(h('p', 'empty', 'The endpoint serves no model.')); return; }
    const ml = h('ul', 'rows ep-models'); ml.setAttribute('aria-label', 'The models the endpoint serves');
    for (const m of ep.models) ml.appendChild(modelRow(m));
    frag.appendChild(ml);
  }
  /** One served (model, profile): what it takes and makes, what a dataset can be made of with it, its capabilities. */
  function modelRow(m) {
    const li = h('li', 'ep-model'); li.dataset.model = m.model; li.dataset.profile = m.profile;
    const who = h('span', 'ep-who'); who.appendChild(h('span', 'title mono', m.model)); who.appendChild(h('span', 'sub mono', m.profile + (m.profile_required ? ' · profile required' : ''))); li.appendChild(who);
    const what = h('span', 'ep-what');
    what.appendChild(h('span', 'title', 'Takes ' + (listed(m.modalities.input) || 'nothing') + ' · makes ' + (listed(m.modalities.output) || 'nothing')));
    const makes = h('span', 'sub ep-makes');
    if (m.makes.length) {
      makes.appendChild(h('b', null, 'A dataset of: '));
      makes.appendChild(document.createTextNode(m.makes.map(x => (x.make === 'image' ? 'images' : 'texts') + ' by ' + x.capability + (Object.keys(x.options).length ? ' (' + optionsOf(x).map(([k, b]) => k + ' ' + bound(b)).join(', ') + ')' : '') + (x.seed ? ', with a seed' : '')).join('; ')));
    } else makes.textContent = 'No dataset can be made with it.';
    what.appendChild(makes);
    const on = m.capabilities.filter(c => c.available), off = m.capabilities.filter(c => !c.available);
    if (on.length) what.appendChild(h('span', 'sub ep-caps', 'Available: ' + on.map(c => c.capability + ' (' + c.input_formats.join(', ') + ' → ' + c.output_formats.join(', ') + ')').join(', ')));
    if (off.length) what.appendChild(h('span', 'sub ep-off', 'Unavailable: ' + off.map(c => c.capability + (c.reason ? ' (' + c.reason + ')' : '')).join(', ')));
    li.appendChild(what);
    li.appendChild(h('span', 'sub ep-load', [m.provider, m.load_state, m.context_tokens ? m.context_tokens.toLocaleString('en-GB') + ' tokens' : null].filter(Boolean).join(' · ')));
    return li;
  }

  // ---- Train: the endpoint's drawer -----------------------------------------------------------------------------------
  let found = null;   // the last answer of find_endpoints, shown until the page is left
  /** The drawer: the endpoint's state; for the owner Set (an address), Clear and Find on this machine; Ask it again. */
  function drawer(aside, act) {
    S.drawer(aside, 'endpoint', () => P.read('endpoint'), (ins, ep) => {
      const st = standing(ep);
      const hd = h('header'); hd.appendChild(h('span', 'kicker', 'Pumas endpoint · a setting of this machine'));
      const t = h('h2', null, ep.address || 'No endpoint set'); t.tabIndex = -1; hd.appendChild(t);
      const meta = h('div', 'ins-meta'); meta.appendChild(S.stateEl(st.tone, st.word)); hd.appendChild(meta); ins.appendChild(hd);
      const dl = h('dl', 'setup'); const put = (k, v) => { dl.appendChild(h('dt', null, k)); dl.appendChild(h('dd', null, v)); };
      put('Address', ep.address || 'none'); put('Answers', ep.address ? (ep.answered ? 'yes' : 'no') : '—');
      if (ep.answered) { put('Version', ep.version || 'not reported'); put('Models', String(ep.models.length)); }
      if (ep.problem && ep.address) put('Problem', ep.problem);
      ins.appendChild(dl);
      ins.appendChild(h('p', 'note', 'The address is kept in Tuldok\'s settings file on this machine, never in the project folder. Generation and suggestions go to it over HTTP; nothing of Pumas runs inside Tuldok.'));
      ins.appendChild(A.group('endpoint:again', [{ id: 'again', label: 'Ask it again', cls: 'btn sm', onClick: () => { P.forget(['endpoint']); act.refresh(); } }]));
      if (!A.may('owner')) { ins.appendChild(h('p', 'note', 'Only the owner of this Tuldok sets the endpoint.')); return; }
      const set = h('div', 'ep-part'); set.appendChild(h('h3', null, ep.address ? 'Set another address' : 'Set the address'));
      set.appendChild(h('p', 'note', 'A numeric loopback HTTP address, such as http://127.0.0.1:8765, without a path. Tuldok asks it once what it serves and keeps it only when it answers.'));
      const f = h('div', 'form');
      f.appendChild(A.group('endpoint:set', [{ id: 'set', label: 'Set', cls: 'btn', who: 'owner', op: 'set_endpoint', busy: 'Asking it…',
        input: { name: 'address', label: 'Address', placeholder: 'http://127.0.0.1:8765', max: 2048, always: true },
        args: s => ({ address: (s.text.address || '').trim() }) }]));
      set.appendChild(f); ins.appendChild(set);
      const find = h('div', 'ep-part'); find.appendChild(h('h3', null, 'Find on this machine'));
      find.appendChild(h('p', 'note', 'Lists the Pumas endpoints that advertise themselves on this machine\'s loopback listeners, to pick from. Nothing is set until you pick one.'));
      const list = h('div', 'ep-found');
      find.appendChild(A.group('endpoint:find', [{ id: 'find', label: 'Find on this machine', cls: 'btn', who: 'owner', op: 'find_endpoints', busy: 'Looking…', local: true,
        done: r => { found = r; putInPlace(list, foundList()); } }]));
      list.appendChild(foundList()); find.appendChild(list); ins.appendChild(find);
      if (ep.address) ins.appendChild(A.group('endpoint:clear', [{ id: 'clear', label: 'Clear the endpoint', cls: 'btn ghost', who: 'owner', op: 'set_endpoint', args: () => ({ address: null }), busy: 'Clearing…',
        confirm: 'Clear the endpoint of this machine: nothing can be generated or suggested here until one is set again. Nothing else changes.' }]));
    });
  }
  /** What Find on this machine found, each with Use this. */
  function foundList() {
    const box = h('div');
    if (!found) return box;
    if (!found.endpoints.length) box.appendChild(h('p', 'empty', 'No Pumas endpoint advertises itself on this machine.'));
    else {
      const ul = h('ul', 'rows');
      for (const e of found.endpoints) {
        const li = h('li', 'with-act'); const t = h('span', 'row ep-hit'); t.style.gridTemplateColumns = 'minmax(0, 1fr)';
        const s = h('span'); s.appendChild(h('span', 'title mono', e.address)); s.appendChild(h('span', 'sub', [e.version ? 'Pumas ' + e.version : 'version not reported', e.component].filter(Boolean).join(' · '))); t.appendChild(s); li.appendChild(t);
        li.appendChild(A.group('endpoint:use:' + e.address, [{ id: 'use', label: 'Use this', cls: 'btn sm', who: 'owner', op: 'set_endpoint', args: () => ({ address: e.address }), busy: 'Asking it…' }], { inline: true }));
        ul.appendChild(li);
      }
      box.appendChild(ul);
    }
    for (const r of found.rejected || []) box.appendChild(h('p', 'small warnline', r.server_url + ' answered, but its advertisement was refused: ' + r.reason));
    return box;
  }

  // ---- Data: the Generate form ------------------------------------------------------------------------------------------
  /** Generate: a new datasets/<name> whose run is the step generate, kept as an unsaved edit. */
  function form(aside, act) {
    const F = forms();
    F.formDrawer(aside, 'data:new:generate', () => Promise.all([P.read('endpoint').catch(error => ({ error })), P.read('definitions', { kind: 'dataset' })]), (ins, [ep, defs]) => {
      const key = 'newgenerate', s = A.slot(key), by = makers(ep), kinds = Object.keys(MAKE_WORD).filter(k => by[k]);
      F.header(ins, 'new dataset · generate', 'Generate a dataset',
        'A dataset made by asking a model the Pumas endpoint serves, one request per item. It is built as any build is, on a machine with an endpoint set; a model need not make the same thing twice.');
      if (!kinds.length) {
        const why = h('div', 'gen-none'); why.setAttribute('role', 'status');
        why.appendChild(h('p', 'failure', ep.error ? 'What the endpoint serves could not be read: ' + ep.error.message
          : !ep.address ? 'No Pumas endpoint is set on this machine, so there is nothing to generate with.'
            : !ep.answered ? 'The Pumas endpoint at ' + ep.address + ' does not answer: ' + (ep.problem || 'no reason was given.')
              : 'The Pumas endpoint at ' + ep.address + ' serves ' + ep.models.length + (ep.models.length === 1 ? ' model' : ' models') + ', and none can make a text or an image now.'));
        why.appendChild(h('p', 'note', 'Generate offers only what a served model can make at the moment the form is opened.'));
        const acts = h('div', 'actions'); acts.appendChild(button('btn', 'The endpoint on the Train tab', 'gen:endpoint', () => act.go('train', 'endpoint'))); acts.appendChild(button('btn ghost', 'Cancel', 'gen:cancel', () => act.select(null)));
        why.appendChild(acts); ins.appendChild(why); return;
      }
      const sets = defs.definitions.filter(d => !d.removed);
      const box = h('div', 'form gen-form');
      const fields = () => {
        const f = document.createDocumentFragment();
        let nameBox = null;
        f.appendChild(F.input(s, key, 'title', 'Title (required)', { max: 200, onInput: () => { if (!s.text.nameTyped && nameBox) { nameBox.value = F.slug(s.text.title || ''); s.text.name = nameBox.value; } } }));
        const nl = F.input(s, key, 'name', 'Name', { max: 120, hint: 'the file is datasets/<name>.json', placeholder: 'made from the title', onInput: v => { s.text.nameTyped = !!v; } });
        nameBox = nl.querySelector('input'); if (!s.text.nameTyped) { nameBox.value = F.slug(s.text.title || ''); s.text.name = nameBox.value; }
        f.appendChild(nl);
        f.appendChild(F.choice(s, key, 'make', 'What to make', kinds.map(k => [k, MAKE_WORD[k]]), kinds[0], redraw));
        const offer = by[s.text.make];
        f.appendChild(F.choice(s, key, 'model', 'Model, of those that make ' + (s.text.make === 'image' ? 'images' : 'texts') + ' now', offer.map(({ m, made }) => [entryKey(m), m.model + ' · ' + m.profile + ' (' + made.capability + ')']), entryKey(offer[0].m), redraw));
        const { m, made } = offer.find(o => entryKey(o.m) === s.text.model);
        if (needsProfile(ep, m)) f.appendChild(h('p', 'small faint gen-line', 'The profile ' + m.profile + ' is written with the model: ' + (m.profile_required ? 'the endpoint requires it.' : 'the endpoint serves ' + m.model + ' with more than one.')));
        const prompts = s.text.from === 'prompts';
        f.appendChild(F.input(s, key, 'prompt', 'Prompt (required)', { area: 3, max: 16000, placeholder: s.text.make === 'image' ? 'A picture of {text}, number {n}.' : 'Write line {n} of a short poem.' }));
        f.appendChild(h('p', 'small faint gen-line', '{n} is replaced by the item\'s number from 1' + (prompts ? '; {text} by the text of the prompting record' : '; with a dataset of prompts, {text} by the text of the prompting record') + '. {{ and }} are written as braces.'));
        const how = h('div', 'ann-field'); how.appendChild(h('h3', null, 'How many'));
        const rd = h('div', 'radio'); rd.setAttribute('role', 'radiogroup'); rd.setAttribute('aria-label', 'How many');
        for (const [v, label] of [['count', 'A count'], ['prompts', 'One for each text record of a dataset of prompts']]) {
          const l = h('label'), i = h('input'); i.type = 'radio'; i.name = 'gen-from'; i.value = v; i.checked = (s.text.from || 'count') === v; i.dataset.key = key + ':field:from-' + v;
          i.addEventListener('change', () => { if (i.checked) { s.text.from = v; redraw(); } }); l.appendChild(i); l.appendChild(h('span', null, label)); rd.appendChild(l);
        }
        how.appendChild(rd);
        if (!prompts) how.appendChild(numberField(s, key, 'count', 'Count (required)', { minimum: 1, maximum: 100000 }, { value: '10', step: 1 }));
        else {
          const two2 = h('div', 'two');
          if (!sets.length) two2.appendChild(h('p', 'failure', 'The project has no dataset to take prompts from.'));
          else two2.appendChild(F.choice(s, key, 'prompts', 'The dataset of prompts', sets.map(d => [d.reference, d.title + ' · ' + d.reference]), sets[0].reference));
          two2.appendChild(numberField(s, key, 'per', 'For each record', { minimum: 1, maximum: 1000 }, { value: '1', step: 1, hint: 'how many for each of its text records' }));
          how.appendChild(two2);
        }
        f.appendChild(how);
        // The seed and the options, as the chosen capability declares them.
        const opts = h('div', 'ann-field gen-opts'); opts.appendChild(h('h3', null, 'Options of ' + made.capability));
        const names = optionsOf(made).map(([n]) => n), need = REQUIRED[s.text.make] || [];
        if (!names.length && !made.seed) opts.appendChild(h('p', 'note', made.capability + ' declares no option Tuldok can set; the endpoint\'s defaults apply.'));
        const grid = h('div', 'gen-grid');
        if (made.seed) grid.appendChild(numberField(s, key, 'seed', 'Seed', { minimum: 0, maximum: 4294967295 }, { step: 1 }));
        for (const n of names) grid.appendChild(numberField(s, key, 'opt:' + n, n + (need.includes(n) ? ' (required)' : ''), made.options[n], { step: 'any' }));
        if (grid.children.length) opts.appendChild(grid);
        const said = [];
        if (made.seed) said.push('Item n is asked with the seed + n − 1; with no seed the endpoint chooses one.');
        if (names.length) said.push('An option left empty is not sent' + (need.length ? ', except ' + listed(need) + ', which an image needs' : '') + '. The bounds are what the endpoint advertises now' + (s.text.make === 'image' ? '; Tuldok asks for at most 2,048 pixels a side.' : '.'));
        if (said.length) opts.appendChild(h('p', 'small faint gen-line', said.join(' ')));
        f.appendChild(opts);
        f.appendChild(F.input(s, key, 'rights', 'Rights (required)', { area: 2, max: 1000, hint: 'what may be done with what is made', placeholder: 'Made by a model; anything may be done with it.' }));
        return f;
      };
      const redraw = () => putInPlace(box, fields());
      box.appendChild(fields());
      ins.appendChild(box);
      ins.appendChild(A.group(key, [
        { id: 'keep', label: 'Keep', cls: 'btn primary', who: 'edit', op: 'set_definition', busy: 'Keeping…',
          args: st => { const o = by[st.text.make].find(x => entryKey(x.m) === st.text.model); return { reference: 'datasets/' + (st.text.name || '').trim(), text: F.textOf(generateDoc(st.text, o.m, o.made, needsProfile(ep, o.m))) }; },
          done: r => { act.select(r.reference); } },
        { id: 'back', label: 'Cancel', cls: 'btn ghost', onClick: () => act.select(null) }
      ]));
      ins.appendChild(h('p', 'note', 'Keep checks the definition and keeps it in Tuldok as an unsaved edit; Save writes it. Building it is planned and requested as any build is; an agent\'s request waits for the owner.'));
    });
  }
  /** A number field whose value lives in the slot; the bounds are its minimum and maximum. */
  function numberField(s, key, name, label, b, { value, step, hint } = {}) {
    const l = forms().input(s, key, name, label, { type: 'number', value, hint: hint || bound(b) });
    const i = l.querySelector('input'); i.min = String(b.minimum); i.max = String(b.maximum); i.step = String(step || 'any'); i.inputMode = step === 1 ? 'numeric' : 'decimal';
    return l;
  }
  const refuse = text => { throw Object.assign(Error(text), { code: 'invalid' }); };
  /** A whole number or a number from the field's text, within its bounds; null when empty and not required. */
  function numberOf(text, label, b, whole, required) {
    const raw = String(text == null ? '' : text).trim();
    if (!raw) { if (required) refuse(label + ' is required.'); return null; }
    const v = Number(raw);
    if (!Number.isFinite(v) || (whole && !Number.isInteger(v))) refuse(label + ' is ' + (whole ? 'a whole number' : 'a number') + '; "' + raw + '" is not.');
    if (v < b.minimum || v > b.maximum) refuse(label + ' ' + raw + ' is outside ' + bound(b) + '.');
    return v;
  }
  /** The definition a generate writes (docs/contracts/project-folder.md, Steps Tuldok provides). */
  function generateDoc(x, m, made, profile) {
    const settings = { make: x.make, model: m.model };
    if (profile) settings.profile = m.profile;
    settings.prompt = (x.prompt || '').trim();
    const prompts = x.from === 'prompts';
    if (prompts) { const per = numberOf(x.per, 'For each record', { minimum: 1, maximum: 1000 }, true, false); if (per !== null && per !== 1) settings.per = per; }
    else settings.count = numberOf(x.count, 'The count', { minimum: 1, maximum: 100000 }, true, true);
    if (made.seed) { const seed = numberOf(x.seed, 'The seed', { minimum: 0, maximum: 4294967295 }, true, false); if (seed !== null) settings.seed = seed; }
    const options = {}, need = REQUIRED[x.make] || [];
    for (const [n, b] of optionsOf(made)) { const v = numberOf(x['opt:' + n], n, b, ['max_tokens', 'width', 'height'].includes(n), need.includes(n)); if (v !== null) options[n] = v; }
    if (Object.keys(options).length) settings.options = options;
    settings.rights = (x.rights || '').trim();
    const run = { step: 'generate' };
    if (prompts) run.inputs = { prompts: x.prompts };
    run.settings = settings;
    return { format: FORMAT, kind: 'dataset', title: (x.title || '').trim(), run };
  }

  return { section, drawer, form };
})();
