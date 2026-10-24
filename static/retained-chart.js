/* Shared pinned Vega renderer. Domain hosts own data, selection and authority. */
(() => {
  'use strict';
  async function specification({path, sha256}, signal) {
    if (!/^\/static\/[a-z0-9-]+\.vl\.json$/.test(path) || !/^[a-f0-9]{64}$/.test(sha256)) throw Error('Invalid pinned chart identity.');
    const reply = await fetch(path, {signal, credentials: 'same-origin', cache: 'no-cache'});
    if (!reply.ok) throw Error('Retained chart specification is unavailable.');
    const reader = reply.body.getReader();
    let raw = new Uint8Array(0);
    try {
      while (true) {
        const {value, done} = await reader.read();
        if (done) break;
        if (raw.byteLength + value.byteLength > 16384) throw Error('Retained chart specification exceeds its budget.');
        const next = new Uint8Array(raw.byteLength + value.byteLength);
        next.set(raw); next.set(value, raw.byteLength); raw = next;
      }
    } finally { await reader.cancel(); }
    const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw))].map(byte => byte.toString(16).padStart(2, '0')).join('');
    if (hash !== sha256) throw Error('Retained chart specification identity differs.');
    return JSON.parse(new TextDecoder().decode(raw));
  }
  function mount(root, pinned, {onError = error => { root.textContent = error.message; }} = {}) {
    let disposed = false, generation = 0, pending, view, observer, detach;
    function clear() {
      ++generation; pending?.abort(); pending = undefined;
      detach?.(); detach = undefined;
      observer?.disconnect(); observer = undefined;
      view?.finalize(); view = undefined;
      root.replaceChildren(); root.removeAttribute('aria-busy');
    }
    async function render(datasets, {signal, onSignal = {}, isCurrent = () => true} = {}) {
      clear();
      if (disposed || signal?.aborted || !isCurrent()) return false;
      if (new TextEncoder().encode(JSON.stringify(datasets)).length > 256 * 1024) throw Error('Retained chart data exceeds its budget.');
      const ticket = generation;
      pending = new AbortController(); const ownSignal = pending.signal;
      signal?.addEventListener('abort', clear, {once: true});
      detach = () => signal?.removeEventListener('abort', clear);
      const active = () => !disposed && ticket === generation && !ownSignal.aborted && !signal?.aborted && isCurrent();
      root.setAttribute('aria-busy', 'true');
      try {
        const base = await specification(pinned, ownSignal);
        if (!active()) return false;
        if (typeof window.vegaEmbed !== 'function' || typeof window.vega?.expressionInterpreter !== 'object') throw Error('Pinned chart assets are unavailable.');
        base.datasets = structuredClone(datasets);
        const deny = () => Promise.reject(Error('Chart URL loading is disabled.'));
        const embedded = await window.vegaEmbed(root, base, {actions: false, defaultStyle: false, tooltip: false,
          mode: 'vega-lite', renderer: 'svg', ast: true, expr: window.vega.expressionInterpreter, loader: {load: deny, sanitize: deny}});
        if (!active()) { embedded.finalize(); return false; }
        view = embedded.view;
        for (const [name, select] of Object.entries(onSignal)) view.addSignalListener(name, (_name, value) => { if (active()) select(value); });
        observer = new ResizeObserver(() => {
          if (active()) void view?.resize().runAsync().catch(error => { if (active()) { clear(); onError(error); } });
        });
        observer.observe(root);
        return true;
      } catch (error) {
        if (!active()) return false;
        clear(); throw error;
      } finally { if (active()) root.setAttribute('aria-busy', 'false'); }
    }
    return {render, clear, resize: () => view?.resize().runAsync(), dispose() { disposed = true; clear(); }};
  }
  window.RetainedChart = Object.freeze({mount});
})();
