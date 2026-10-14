'use strict';
// Follow the real workspace navigation before asserting/capturing a panel.
// Never unhide owner-controlled content or change its workflow state.
async function revealWorkbenchControl(evaluate, selector) {
  await evaluate(`(() => {
    const target = document.querySelector(${JSON.stringify(selector)});
    if(!target) throw Error('Missing workspace capture target');
    const panel = target.closest('.workspace-panel');
    if(panel) {
      const key = panel.id.replace('workspace-panel-', '');
      const button = [...document.querySelectorAll('[data-workspace-panel]')].find(node => node.dataset.workspacePanel === key);
      if(!button) throw Error('Missing workspace navigation');
      button.click();
    } else {
      const drawer = document.getElementById('workspace-tools');
      if(drawer?.open) document.getElementById('workspace-tools-close').click();
    }
    const disclosures = [];
    for(let node = target; node; node = node.parentElement) {
      if(node.hidden) throw Error('Capture target is unavailable in the current workflow');
      if(node.tagName === 'DETAILS') disclosures.unshift(node);
    }
    for(const disclosure of disclosures) {
      if(!disclosure.open) disclosure.querySelector(':scope > summary').click();
    }
  })()`);
}
module.exports = {revealWorkbenchControl};
