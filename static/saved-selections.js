'use strict';
let savedLoadBusy = false, savedLoadEpoch = 0, savedListEpoch = 0;
let savedSets = new Map(), savedMembershipKey = JSON.stringify(releaseBody().items);
function savedStatus(message) { $('saved-selection-status').textContent = message; }
function cancelSavedLoad(message = 'Opening cancelled. Current selection retained.') {
  ++savedLoadEpoch; savedLoadBusy = false;
  $('cancel-selection-load').hidden = true; releaseButtons();
  if(message) savedStatus(message);
}
function savedSelectionChanged() {
  const key = JSON.stringify(releaseBody().items);
  if(key === savedMembershipKey) return;
  savedMembershipKey = key;
  cancelSavedLoad('Current selection changed. Saved sets retain their original membership and revisions.');
  $('saved-selection-issues').replaceChildren();
}
async function refreshSavedSets(preferred = $('saved-selection').value) {
  const epoch = ++savedListEpoch, result = await api('selections');
  if(epoch !== savedListEpoch) return;
  savedSets = new Map(result.selections.map(set=>[set.id,set]));
  const empty = document.createElement('option'); empty.value='';empty.textContent='Choose a saved selection';
  $('saved-selection').replaceChildren(empty);
  for(const set of savedSets.values()) {
    const option=document.createElement('option');option.value=set.id;
    option.textContent=`${set.name} · ${set.member_count} fixed records`; $('saved-selection').append(option);
  }
  $('saved-selection').value=savedSets.has(preferred)?preferred:'';
}
async function openSavedSelection(id = $('saved-selection').value, navigate = true) {
  if(!id) throw Error('Choose a saved selection.');
  if(savedLoadBusy) return;
  const epoch=++savedLoadEpoch, key=JSON.stringify(releaseBody().items);
  savedLoadBusy=true;invalidateRelease();$('cancel-selection-load').hidden=false;
  savedStatus('Opening fixed membership and checking saved revisions and source bytes…');
  try {
    const result=await api('selections/'+id);
    if(epoch!==savedLoadEpoch || key!==JSON.stringify(releaseBody().items)) return;
    savedLoadBusy=false;$('cancel-selection-load').hidden=true;
    selected.clear();for(const item of result.selection.items) selected.set(item.id,item);
    savedMembershipKey=JSON.stringify(releaseBody().items);
    selection();invalidateRelease();
    $('saved-selection').value=savedSets.has(id)?id:'';
    $('saved-selection-issues').replaceChildren();
    for(const member of result.members.filter(member=>member.status!=='ok')) {
      const li=document.createElement('li');
      li.textContent=`${member.item.name} (${member.item.id}) · ${member.status.replaceAll('_',' ')}: ${member.message}`;
      $('saved-selection-issues').append(li);
    }
    savedStatus(`Opened “${result.selection.name}”: ${result.selection.member_count} fixed records. `+
      (result.current?'Saved revisions are current. Preview before exporting.':'Unavailable or changed members are retained; no replacements were selected.'));
    if(navigate && location.hash !== '#selection='+id) history.pushState(null,'','#selection='+id);
    await refresh();
  } catch(error) { if(epoch===savedLoadEpoch) savedStatus(error.message); }
  finally { if(epoch===savedLoadEpoch) {savedLoadBusy=false;$('cancel-selection-load').hidden=true;releaseButtons();} }
}
action('save-selection-form',async()=>{
  const name=$('selection-name').value, items=releaseBody().items;
  const result=await api('selections',{name,items});
  await refreshSavedSets(result.id);
  savedStatus(`Saved “${result.name}”: ${result.member_count} fixed records. Review states are unchanged.`);
},'submit');
$('load-selection').addEventListener('click',event=>{event.preventDefault();openSavedSelection().catch(error=>savedStatus(error.message));});
$('cancel-selection-load').addEventListener('click',()=>cancelSavedLoad());
$('saved-selection').addEventListener('change',()=>cancelSavedLoad('Choose Open fixed selection to replace the current selection.'));
action('refresh-selections',()=>refreshSavedSets());
action('rename-selection-form',async()=>{
  const set=savedSets.get($('saved-selection').value);if(!set)throw Error('Choose a saved selection.');
  const result=await api('selections/'+set.id+'/rename',{revision:set.revision,name:$('selection-rename').value});
  await refreshSavedSets(result.id);savedStatus(`Renamed to “${result.name}”. Membership is unchanged.`);
},'submit');
action('delete-selection',async()=>{
  const set=savedSets.get($('saved-selection').value);if(!set)throw Error('Choose a saved selection.');
  if(!confirm(`Delete saved set “${set.name}”? Records and the current selection are retained.`))return;
  cancelSavedLoad(null);
  await api('selections/'+set.id+'/delete',{revision:set.revision});
  await refreshSavedSets();savedStatus('Saved set deleted. Records and the current selection are retained.');
});
function navigateSavedSelection() {
  cancelSavedLoad(null);
  const id=new URLSearchParams(location.hash.slice(1)).get('selection');
  if(id) return openSavedSelection(id,false);
  selected.clear();selection();invalidateRelease();
  $('saved-selection-issues').replaceChildren();savedStatus('No saved set open. Choose one to reopen fixed membership.');
  return refresh();
}
window.addEventListener('popstate',()=>navigateSavedSelection().catch(error=>savedStatus(error.message)));
window.addEventListener('pagehide',()=>{cancelSavedLoad(null);++savedListEpoch;});
window.addEventListener('pageshow',event=>{
  if(!event.persisted) return;
  if(new URLSearchParams(location.hash.slice(1)).has('selection')) navigateSavedSelection().catch(error=>savedStatus(error.message));
  else {invalidateRelease();refresh().catch(error=>savedStatus(error.message));}
});
refreshSavedSets().then(()=>{
  if(new URLSearchParams(location.hash.slice(1)).has('selection')) return navigateSavedSelection();
}).catch(error=>savedStatus(error.message));
