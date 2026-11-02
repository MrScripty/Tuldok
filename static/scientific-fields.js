'use strict';
// Workbench transport and editor ownership for the shared field inspector.
const scientificInspector=window.ScientificFieldInspector({
  root:document.getElementById('scientific-inspection'),
  isCurrent:record=>current?.id===record.id&&current.content_hash===record.content_hash,
  downloadURL:record=>'/api/workbench/asset/'+record.id,
  async readSlice(record,selection,signal){
    const response=await (globalThis.TuldokAuth?.fetch||fetch)('/api/workbench/records/'+record.id+'/scientific?'+new URLSearchParams(selection),{signal});
    const value=await response.json();if(!response.ok)throw Error(value.error||'Scientific slice unavailable.');return value;
  }
});
function scientificShown(record){
  scientificInspector.show(record);
  if(record.kind==='field_sequence')$('scientific-note').value=record.annotation?.note||'';
}
window.addEventListener('pagehide',()=>scientificInspector.clear());
