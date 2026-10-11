'use strict';
// Presentation only: move focus and expose the existing forms without cloning
// controls, submitting requests, resetting edits, or taking over their owners.
(() => {
  const drawer = document.getElementById('workspace-tools');
  const title = document.getElementById('workspace-tools-title');
  const close = document.getElementById('workspace-tools-close');
  const panels = [...drawer.querySelectorAll('.workspace-panel')];
  const labels = {import:'Import assets',generate:'Generate candidates',export:'Export selected data',collection:'Manage collection'};
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
  new MutationObserver(syncNotice).observe(notice,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});
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
