'use strict';
// Presentation only: move focus and expose the existing forms without cloning
// controls, submitting requests, resetting edits, or taking over their owners.
(() => {
  // Embedded Data has its own presentation/context owner. Keep that document's
  // nodes in place for workspaces-data.js, including its existing tools drawer.
  if (window.parent !== window && new URLSearchParams(location.search).get('workspace') === '1') return;
  document.documentElement.classList.add('compact-workbench');
  const byId = id => document.getElementById(id);
  const element = (tag, className) => {
    const node = document.createElement(tag);
    if(className) node.className = className;
    return node;
  };
  const disclosure = (id, label) => {
    const node = element('details', 'compact-details'); node.id = id;
    const summary = element('summary'); summary.textContent = label;
    node.append(summary); return node;
  };
  const labels = {import:'Import assets',generate:'Generate candidates',export:'Export selected data',collection:'Manage collection'};
  const drawer = element('dialog'); drawer.id = 'workspace-tools';
  drawer.setAttribute('aria-labelledby', 'workspace-tools-title');
  const heading = element('div', 'drawer-heading'), title = element('h2');
  title.id = 'workspace-tools-title'; title.textContent = 'Workspace tools';
  const close = element('button'); close.id = 'workspace-tools-close';
  close.type = 'button'; close.textContent = 'Close tools';
  heading.append(title, close); drawer.append(heading);
  const panels = Object.keys(labels).map(key => {
    const panel = element('div', 'workspace-panel');
    panel.id = 'workspace-panel-' + key; panel.hidden = true;
    drawer.append(panel); return panel;
  });
  const panelFor = key => byId('workspace-panel-' + key);
  document.body.append(drawer);
  const toolbar = element('nav', 'workspace-toolbar');
  toolbar.setAttribute('aria-label', 'Workspace tools');
  function toolButton(key, label) {
    const button = element('button'); button.type = 'button';
    button.dataset.workspacePanel = key; button.textContent = label;
    button.setAttribute('aria-controls', drawer.id);
    button.setAttribute('aria-haspopup', 'dialog'); return button;
  }
  toolbar.append(toolButton('import','Import assets'), toolButton('generate','Generate'), toolButton('export','Export'));
  toolbar.lastElementChild.append(byId('selection'));
  document.querySelector('header').append(toolbar);

  const collection = document.querySelector('main > .collection');
  const collectionTitle = collection.querySelector('h2');
  collectionTitle.id = 'collection-title'; collection.setAttribute('aria-labelledby', collectionTitle.id);
  collectionTitle.after(toolButton('collection', 'Manage collection'));
  for(const id of ['saved-search-panel','saved-selection-panel','curation-panel']) {
    panelFor('collection').append(byId(id));
  }
  const filters = byId('filters'), advanced = disclosure('advanced-filters','More filters');
  const typeRow = byId('kind').closest('.row');
  for(const id of ['task-filter','review-filter']) advanced.append(byId(id).closest('label'));
  const search = byId('query').closest('label'), submit = filters.querySelector(':scope > button');
  for(const node of [...filters.children]) {
    if(node !== search && node !== typeRow && node !== submit) advanced.append(node);
  }
  filters.insertBefore(advanced,submit);
  submit.classList.add('search-button');
  const collectionSummary = disclosure('collection-summary','Collection analysis');
  byId('analysis').before(collectionSummary); collectionSummary.append(byId('analysis'));

  const editor = byId('editor'), editorSection = document.querySelector('main > .editor');
  const recordHeading = element('div','record-heading'), state = element('span','record-state');
  state.id = 'record-state'; recordHeading.append(byId('record-name'),state);
  const source = element('div','source-pane'), annotation = element('div','annotation-pane');
  source.setAttribute('role','region'); source.setAttribute('aria-label','Source asset');
  annotation.setAttribute('role','region'); annotation.setAttribute('aria-label','Annotation inspector');
  // Explicit supported source surfaces, including field sequences when their
  // owner is present in a later admitted composition; no inspection is cloned.
  for(const id of ['image-frame','asset-text','audio-inspection','sequence-inspection','pointcloud-inspection','scientific-inspection','volume-inspection','mesh-inspection']) {
    const node = byId(id); if(node) source.append(node);
  }
  for(const node of [...editor.children]) annotation.append(node);
  const annotationTitle = element('h2'); annotationTitle.textContent = 'Annotation';
  annotation.prepend(annotationTitle);
  editor.append(recordHeading,source,annotation);
  const evidence = disclosure('record-evidence','Source groups & provenance');
  const groups = byId('groups').closest('label'); groups.before(evidence);
  evidence.append(groups,byId('record-provenance'));
  const help = disclosure('annotation-help','Task & labeling help');
  byId('classification-help').before(help); help.append(byId('classification-help'));
  byId('save').parentElement.classList.add('editor-actions');
  const recordTools = disclosure('record-tools','Record tools');
  editorSection.append(recordTools);
  for(const node of [...editorSection.querySelectorAll(':scope > details')]) {
    if(node !== recordTools) recordTools.append(node);
  }
  // Route whole existing tool sections, including every current import, by
  // their operation owner. Future additions remain available in Import assets.
  const aside = document.querySelector('main > aside');
  for(const section of [...aside.children]) {
    const key = section.querySelector('#generate-form, #grounded-form') ? 'generate'
      : section.querySelector('#release-form, #response-release-form, #preference-release-form') ? 'export' : 'import';
    panelFor(key).append(section);
  }
  aside.remove();
  let opener = null;
  function openPanel(button) {
    const key = button.dataset.workspacePanel;
    if(!labels[key]) return;
    panels.forEach(panel => panel.hidden = panel.id !== 'workspace-panel-' + key);
    title.textContent = labels[key];
    opener = button;
    if(!drawer.open) drawer.showModal();
    close.focus();
  }
  document.querySelectorAll('[data-workspace-panel]').forEach(button => {
    button.addEventListener('click', () => openPanel(button));
  });
  function closePanel() {
    drawer.close();
    if(opener?.isConnected) opener.focus();
  }
  close.addEventListener('click', closePanel);
  drawer.addEventListener('cancel', event => { event.preventDefault(); closePanel(); });
  drawer.addEventListener('close', () => { if(!drawer.open && opener?.isConnected) opener.focus(); });
  // Invalid controls can live inside collapsed help/advanced sections. Expose
  // their ancestors before the browser focuses them; retain native validation.
  document.addEventListener('invalid', event => {
    for(let parent = event.target.parentElement; parent; parent = parent.parentElement) {
      if(parent.tagName === 'DETAILS') parent.open = true;
    }
  }, true);
  // Existing owners report some operations globally. Mirror only that public
  // status inside the modal, where its announcement remains accessible.
  const notice = document.getElementById('notice');
  const status = document.createElement('p');
  status.id = 'workspace-tools-status'; status.setAttribute('role','status');
  status.setAttribute('aria-live','polite');
  drawer.querySelector('.drawer-heading').after(status);
  function syncNotice() {
    status.textContent = notice.textContent;
    status.classList.toggle('error',notice.classList.contains('error'));
  }
  const observer = new MutationObserver(syncNotice);
  observer.observe(notice,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});
  window.addEventListener('pagehide', event => { if(!event.persisted) observer.disconnect(); });
  syncNotice();
  // Reflect existing record state without changing review or selection.
  window.workbenchLayoutRecordShown = record => {
    document.getElementById('record-state').textContent = 'Saved: ' + record.review.replaceAll('_',' ') + ' · revision ' + record.revision;
    document.querySelectorAll('.record button[data-record-id]').forEach(button => {
      if(button.dataset.recordId === record.id) button.setAttribute('aria-current','true');
      else button.removeAttribute('aria-current');
    });
  };
  if(typeof current !== 'undefined' && current) window.workbenchLayoutRecordShown(current);
})();
