'use strict';
// A small Markdown renderer for a model's card. It builds elements and text
// nodes only: no project text is ever assigned as markup. It covers what the
// cards use: ATX and setext headings, paragraphs, bold and italic, inline
// code, fenced code blocks, nested lists, block quotes, rules and tables.
// Links and images are shown as their text (a link's address is its title);
// nothing on the page is fetched or opened from a card.
window.TuldokMarkdown = (() => {
  const h = (tag, cls) => { const n = document.createElement(tag); if (cls) n.className = cls; return n; };
  const BLANK = /^\s*$/;
  const FENCE = /^( {0,3})(`{3,}|~{3,})(.*)$/;
  const HEADING = /^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$/;
  const RULE = /^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$/;
  const QUOTE = /^ {0,3}> ?/;
  const ITEM = /^( {0,3})([-*+]|\d{1,9}[.)])([ \t]+|$)(.*)$/;
  const SETEXT = /^ {0,3}(=+|-+)[ \t]*$/;
  const ESCAPABLE = /[\\`*_{}[\]()#+\-.!|>~<]/;
  const indentOf = line => line.match(/^ */)[0].length;
  const detab = line => line.replace(/\t/g, '    ');

  // ---- Inline -------------------------------------------------------------
  function closer(text, delimiter, from) {
    for (let j = text.indexOf(delimiter, from); j >= 0; j = text.indexOf(delimiter, j + 1)) {
      if (j === from || /\s/.test(text[j - 1])) continue;
      const after = text[j + delimiter.length];
      if (delimiter.length === 1 && after === delimiter) { j++; continue; }   // part of a double
      if (delimiter[0] === '_' && after && /[A-Za-z0-9]/.test(after)) continue;  // intraword underscore
      return j;
    }
    return -1;
  }
  function bracket(text, from) {   // index of the ] that closes the [ at from, or -1
    let depth = 0;
    for (let j = from; j < text.length; j++) {
      if (text[j] === '\\') { j++; continue; }
      if (text[j] === '[') depth++;
      else if (text[j] === ']' && --depth === 0) return j;
    }
    return -1;
  }
  function inline(text, parent) {
    let buffer = '', i = 0;
    const flush = () => { if (buffer) { parent.appendChild(document.createTextNode(buffer)); buffer = ''; } };
    while (i < text.length) {
      const c = text[i];
      if (c === '\\' && i + 1 < text.length && ESCAPABLE.test(text[i + 1])) { buffer += text[i + 1]; i += 2; continue; }
      if (c === '`') {
        let n = 1; while (text[i + n] === '`') n++;
        const fence = '`'.repeat(n);
        let end = text.indexOf(fence, i + n);
        while (end >= 0 && text[end + n] === '`') { let k = end; while (text[k] === '`') k++; end = text.indexOf(fence, k); }
        if (end < 0) { buffer += fence; i += n; continue; }
        let body = text.slice(i + n, end).replace(/\n/g, ' ');
        if (body.length > 2 && body[0] === ' ' && body[body.length - 1] === ' ' && body.trim()) body = body.slice(1, -1);
        flush(); const code = h('code'); code.textContent = body; parent.appendChild(code); i = end + n; continue;
      }
      if (c === '*' || c === '_') {
        let n = 1; while (text[i + n] === c && n < 3) n++;
        const before = text[i - 1], next = text[i + n];
        const opens = next && !/\s/.test(next) && !(c === '_' && before && /[A-Za-z0-9]/.test(before));
        let done = false;
        for (let size = n; opens && size >= 1 && !done; size--) {
          const delimiter = c.repeat(size), end = closer(text, delimiter, i + size);
          if (end < 0 || end === i + size) continue;
          flush();
          const inner = text.slice(i + size, end);
          let outer, target;
          if (size === 3) { outer = h('strong'); target = h('em'); outer.appendChild(target); }
          else { outer = target = h(size === 2 ? 'strong' : 'em'); }
          inline(inner, target); parent.appendChild(outer); i = end + size; done = true;
        }
        if (!done) { buffer += c.repeat(n); i += n; }
        continue;
      }
      if (c === '[' || (c === '!' && text[i + 1] === '[')) {
        const open = c === '!' ? i + 1 : i, close = bracket(text, open);
        if (close > 0 && text[close + 1] === '(') {
          const end = text.indexOf(')', close + 2);
          if (end > 0) {
            const label = text.slice(open + 1, close), target = text.slice(close + 2, end).trim().split(/\s+/)[0] || '';
            flush();
            const span = h('span', 'link'); span.title = target;
            if (c === '!') span.appendChild(document.createTextNode('image: ' + (label || target)));
            else inline(label, span);
            parent.appendChild(span); i = end + 1; continue;
          }
        }
        buffer += c; i++; continue;
      }
      if (c === '<') {
        const auto = /^<((?:https?|mailto|file):[^\s<>]+)>/.exec(text.slice(i));
        if (auto) { flush(); const span = h('span', 'link'); span.title = auto[1]; span.textContent = auto[1]; parent.appendChild(span); i += auto[0].length; continue; }
      }
      if (c === '\n') {
        if (/ {2,}$/.test(buffer)) { buffer = buffer.replace(/ +$/, ''); flush(); parent.appendChild(h('br')); }
        else buffer += ' ';
        i++; continue;
      }
      buffer += c; i++;
    }
    flush();
  }

  // ---- Tables -------------------------------------------------------------
  function cells(line) {
    let row = line.trim();
    if (row.startsWith('|')) row = row.slice(1);
    if (row.endsWith('|') && !row.endsWith('\\|')) row = row.slice(0, -1);
    const out = []; let cell = '', code = 0;
    for (let i = 0; i < row.length; i++) {
      const c = row[i];
      if (c === '\\' && row[i + 1] === '|') { cell += '|'; i++; continue; }
      if (c === '`') code = code ? 0 : 1;
      if (c === '|' && !code) { out.push(cell.trim()); cell = ''; continue; }
      cell += c;
    }
    out.push(cell.trim());
    return out;
  }
  const isDelimiterRow = line => line.includes('-') && /^[\s|:-]+$/.test(line) && cells(line).every(cell => /^:?-+:?$/.test(cell));
  function startsTable(lines, i) { return lines[i].includes('|') && i + 1 < lines.length && isDelimiterRow(lines[i + 1]) && cells(lines[i]).length === cells(lines[i + 1]).length; }
  function table(lines, i, parent) {
    const head = cells(lines[i]), align = cells(lines[i + 1]).map(cell => cell.startsWith(':') && cell.endsWith(':') ? 'center' : cell.endsWith(':') ? 'right' : '');
    const wrap = h('div', 'tbl'), t = h('table'), thead = h('thead'), tr = h('tr');
    head.forEach((cell, k) => { const th = h('th'); if (align[k]) th.style.textAlign = align[k]; inline(cell, th); tr.appendChild(th); });
    thead.appendChild(tr); t.appendChild(thead);
    const tbody = h('tbody'); i += 2;
    for (; i < lines.length && !BLANK.test(lines[i]) && lines[i].includes('|'); i++) {
      const row = cells(lines[i]), r = h('tr');
      for (let k = 0; k < head.length; k++) { const td = h('td'); if (align[k]) td.style.textAlign = align[k]; inline(row[k] || '', td); r.appendChild(td); }
      tbody.appendChild(r);
    }
    t.appendChild(tbody); wrap.appendChild(t); parent.appendChild(wrap);
    return i;
  }

  // ---- Lists --------------------------------------------------------------
  function list(lines, i, parent) {
    const first = ITEM.exec(lines[i]), base = first[1].length, ordered = /\d/.test(first[2]);
    const node = h(ordered ? 'ol' : 'ul');
    if (ordered && parseInt(first[2], 10) !== 1) node.start = parseInt(first[2], 10);
    let loose = false;
    while (i < lines.length) {
      const m = ITEM.exec(lines[i]);
      if (!m || m[1].length !== base || /\d/.test(m[2]) !== ordered) break;
      const offset = m[1].length + m[2].length + Math.min(Math.max(m[3].length, 1), 4);
      const body = [m[4]]; i++;
      let blankRun = 0;
      while (i < lines.length) {
        const line = lines[i];
        if (BLANK.test(line)) { blankRun++; body.push(''); i++; continue; }
        const indent = indentOf(line);
        if (indent >= offset || (indent > base && !ITEM.test(line))) { body.push(line.slice(Math.min(indent, offset))); blankRun = 0; i++; continue; }
        if (indent > base && ITEM.test(line)) { body.push(line.slice(Math.min(indent, offset))); blankRun = 0; i++; continue; }
        if (!blankRun && !ITEM.test(line) && !FENCE.test(line) && !HEADING.test(line) && !QUOTE.test(line) && !RULE.test(line)) { body.push(line.trim()); i++; continue; }   // lazy continuation
        break;
      }
      while (body.length && body[body.length - 1] === '') body.pop();
      if (blankRun && i < lines.length && ITEM.test(lines[i])) loose = true;
      const li = h('li'); blocks(body, li); node.appendChild(li);
    }
    if (!loose) for (const li of node.children) {   // a tight item shows its first paragraph without the paragraph box
      const p = li.firstElementChild;
      if (p && p.tagName === 'P') { while (p.firstChild) li.insertBefore(p.firstChild, p); p.remove(); }
    }
    parent.appendChild(node);
    return i;
  }

  // ---- Blocks -------------------------------------------------------------
  function interrupts(lines, i) {
    const line = lines[i];
    return FENCE.test(line) || HEADING.test(line) || RULE.test(line) || QUOTE.test(line) || ITEM.test(line) || startsTable(lines, i);
  }
  function blocks(lines, parent) {
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (BLANK.test(line)) { i++; continue; }
      let m = FENCE.exec(line);
      if (m) {
        const indent = m[1].length, mark = m[2], body = [];
        i++;
        while (i < lines.length) {
          const close = FENCE.exec(lines[i]);
          if (close && close[2][0] === mark[0] && close[2].length >= mark.length && !close[3].trim()) { i++; break; }
          body.push(lines[i].slice(Math.min(indentOf(lines[i]), indent))); i++;
        }
        const pre = h('pre'), code = h('code'); code.textContent = body.join('\n');
        const language = m[3].trim().split(/\s+/)[0]; if (language) code.dataset.language = language;
        pre.appendChild(code); parent.appendChild(pre); continue;
      }
      m = HEADING.exec(line);
      if (m) { const n = h('h' + m[1].length); inline(m[2] || '', n); parent.appendChild(n); i++; continue; }
      if (RULE.test(line)) { parent.appendChild(h('hr')); i++; continue; }
      if (QUOTE.test(line)) {
        const body = [];
        while (i < lines.length && !BLANK.test(lines[i]) && (QUOTE.test(lines[i]) || !interrupts(lines, i))) { body.push(lines[i].replace(QUOTE, '')); i++; }
        const quote = h('blockquote'); blocks(body, quote); parent.appendChild(quote); continue;
      }
      if (startsTable(lines, i)) { i = table(lines, i, parent); continue; }
      if (ITEM.test(line)) { i = list(lines, i, parent); continue; }
      const body = [line.trim()]; i++;
      let level = 0;
      while (i < lines.length && !BLANK.test(lines[i])) {
        const s = SETEXT.exec(lines[i]);
        if (s) { level = s[1][0] === '=' ? 1 : 2; i++; break; }
        if (interrupts(lines, i)) break;
        body.push(lines[i].replace(/^\s+/, '')); i++;
      }
      const n = h(level ? 'h' + level : 'p'); inline(body.join('\n'), n); parent.appendChild(n);
    }
  }

  /** A div.card-md holding text rendered as elements. */
  function render(text) {
    const root = h('div', 'card-md');
    blocks(String(text).replace(/\r\n?/g, '\n').split('\n').map(detab), root);
    return root;
  }
  return { render };
})();
