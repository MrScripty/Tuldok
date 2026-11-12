'use strict';
// A served project folder: its name and folder, and its report. Contract
// versions and hashes are read from /api/agent/capabilities, never pinned here.
(() => {
  const $ = id => document.getElementById(id);
  const dark = window.matchMedia('(prefers-color-scheme: dark)');
  let contracts = null, loading = false;

  async function json(response) {
    const value = await response.json();
    if (!response.ok) throw Error(value.error || 'The request was refused.');
    return value;
  }

  async function selection(name) {
    if (!contracts) {
      const manifest = await json(await window.TuldokAuth.fetch('/api/agent/capabilities', {cache: 'no-store'}));
      contracts = new Map(manifest.operations.map(operation => {
        const newest = operation.contracts.reduce((a, b) => (b.version > a.version ? b : a));
        return [operation.id, operation.id + '/' + newest.version + '/' + newest.sha256];
      }));
    }
    if (!contracts.has(name)) throw Error('This Tuldok does not offer ' + name + '.');
    return contracts.get(name);
  }

  async function call(name, body) {
    const response = await window.TuldokAuth.fetch('/api/project/' + name, {
      method: 'POST', cache: 'no-store',
      headers: {'Content-Type': 'application/json', 'Tuldok-Operation-Contract': await selection('project.' + name)},
      body: JSON.stringify(body)});
    return json(response);
  }

  async function load() {
    if (loading) return;
    loading = true;
    $('project-reload').disabled = true;
    $('project-error').hidden = true;
    $('project-status').textContent = 'Reading the project…';
    try {
      const summary = await call('summary', {});
      $('project-name').textContent = summary.name;
      document.title = summary.name + ' · Tuldok';
      $('project-folder').textContent = summary.folder;
      const report = await call('report', {theme: dark.matches ? 'dark' : 'light'});
      $('project-report').srcdoc = report.html;
      $('project-status').textContent = 'Read at ' + new Date().toLocaleTimeString() + '.';
    } catch (error) {
      contracts = null;
      $('project-status').textContent = '';
      $('project-error').textContent = error.message;
      $('project-error').hidden = false;
    } finally {
      loading = false;
      $('project-reload').disabled = false;
    }
  }

  function start() {
    $('project-reload').addEventListener('click', load);
    dark.addEventListener('change', load);
    window.addEventListener('tuldok-session', load);
    load();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once: true});
  else start();
})();
