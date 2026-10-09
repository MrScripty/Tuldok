'use strict';
// Dynamic criteria have no authority over fixed selections, editor drafts or release proofs.
const searchFields = {q:'query',kind:'kind',task:'task-filter',review:'review-filter',sort:'sort',label:'label-filter',group:'group-filter',rights:'rights-filter'};
let savedSearches = new Map(), searchLife = 0, searchListEpoch = 0, searchOpenEpoch = 0, searchFilterIntent = 0;
let searchDeparted = false, searchOpening = false, searchWriting = false;
function searchStatus(message) { $('saved-search-status').textContent = message; }
function searchRaw() { return JSON.stringify([...Object.values(searchFields).map(id=>$(id).value),$('exact-filter-format').value]); }
function searchEntered() {
  return {q:$('query').value,kind:$('kind').value,task:$('task-filter').value,review:$('review-filter').value,sort:$('sort').value,
    ...Object.fromEntries(exactFilters.map(([key,name])=>[key,exactFilterValue(key,name)]))};
}
function searchString(value,limit) { return typeof value === 'string' && Array.from(value).length<=limit && !/[\uD800-\uDFFF]/u.test(value); }
function searchKeys(value,keys) { return value && typeof value==='object' && !Array.isArray(value) && Object.keys(value).sort().join('|')===keys.slice().sort().join('|'); }
function validateSearch(value,expected) {
  if(!searchKeys(value,['id','name','revision','criteria','created_at','updated_at','mode','schema_version']) || !/^[a-f0-9]{32}$/.test(value.id) || typeof value.id!=='string' || (expected && value.id!==expected)
    || !searchString(value.name,120) || !value.name.trim() || !Number.isSafeInteger(value.revision) || value.revision<1 || value.mode!=='dynamic' || value.schema_version!==1
    || !searchString(value.created_at,64) || !Number.isFinite(Date.parse(value.created_at)) || !searchString(value.updated_at,64) || !Number.isFinite(Date.parse(value.updated_at))) throw Error('Invalid saved-search receipt. Refresh the list before opening.');
  const c=value.criteria,limits={q:200,kind:20,task:40,review:40,sort:20,label:80,group:120,rights:1000};
  if(!searchKeys(c,Object.keys(searchFields)) || !Object.entries(limits).every(([key,limit])=>searchString(c[key],limit)) || /[\r\n]/.test(c.q)
    || !['','image','text','sequence','mesh','pointcloud'].includes(c.kind) || !['','draft','human_reviewed','programmatically_verified'].includes(c.review)
    || !['','newest','oldest','name','review'].includes(c.sort) || !['','image_detection','image_classification','image_caption','text_classification','text_entities','sequence_transport','mesh_geometry','pointcloud_geometry'].includes(c.task)) throw Error('Unsupported saved-search criteria.');
  return value;
}
function cancelSearchOpen(message='Opening cancelled. Current filters retained.') {
  ++searchOpenEpoch; searchOpening=false;$('cancel-search-open').hidden=true;
  if(message && !searchDeparted) searchStatus(message);
}
async function refreshSearches(preferred=$('saved-search').value,owner=()=>true) {
  const epoch=++searchListEpoch,life=searchLife;
  let data;
  try {data=await api('searches');} catch(error) {if(!searchDeparted&&life===searchLife&&epoch===searchListEpoch&&owner())throw error;return;}
  if(searchDeparted || life!==searchLife || epoch!==searchListEpoch || !owner()) return;
  if(!searchKeys(data,['searches']) || !Array.isArray(data.searches) || data.searches.length>100) throw Error('Invalid saved-search list.');
  const rows=data.searches.map(row=>validateSearch(row));
  if(new Set(rows.map(row=>row.id)).size!==rows.length) throw Error('Duplicate saved-search list identities.');
  savedSearches=new Map(rows.map(row=>[row.id,row]));
  const empty=document.createElement('option');empty.value='';empty.textContent='Choose a saved dynamic search';$('saved-search').replaceChildren(empty);
  for(const row of rows) {const option=document.createElement('option');option.value=row.id;option.textContent=row.name+' · current results';$('saved-search').append(option);}
  $('saved-search').value=savedSearches.has(preferred)?preferred:'';
}
async function openSearch(id=$('saved-search').value) {
  if(!id || searchDeparted || searchOpening) return;
  ++searchListEpoch;
  const epoch=++searchOpenEpoch,life=searchLife,intent=searchFilterIntent,query=queryEpoch,raw=searchRaw(),chosen=$('saved-search').value;
  const owns=()=>!searchDeparted&&life===searchLife&&epoch===searchOpenEpoch&&intent===searchFilterIntent&&chosen===$('saved-search').value;
  let canReport=()=>owns()&&query===queryEpoch&&raw===searchRaw();
  searchOpening=true;$('cancel-search-open').hidden=false;searchStatus('Opening stored criteria against the current collection…');
  try {
    const row=await api('searches/'+id);
    if(!canReport()) {if(owns())searchStatus('Current filters or query changed. Open again deliberately to apply stored criteria.');return;}
    validateSearch(row,id);
    for(const [key,control] of Object.entries(searchFields)) if(!['label','group','rights'].includes(key)) $(control).value=row.criteria[key];
    $('exact-filter-format').value='json';exactFilterFormat='json';
    for(const [key,,limit] of exactFilters) {$(key+'-filter').maxLength=limit*12+2;$(key+'-filter').value=row.criteria[key]===''?'':JSON.stringify(row.criteria[key]);}
    offset=0;const restored=searchRaw(),expected=queryEpoch+1;
    canReport=()=>owns()&&restored===searchRaw()&&queryEpoch===expected;
    await refresh(canReport);
    if(canReport()) searchStatus(`Opened “${row.name}”: dynamic current results. Fixed selections and review states are unchanged.`);
  } catch(error) {if(canReport())searchStatus(error.message);}
  finally {if(life===searchLife && epoch===searchOpenEpoch){searchOpening=false;$('cancel-search-open').hidden=true;}}
}
function searchWrite(id,fn,event='click') {
  $(id).addEventListener(event,async e=>{
    e.preventDefault();if(searchWriting||searchDeparted)return;
    if(id==='delete-search')cancelSearchOpen(null);
    const life=searchLife,chosen=$('saved-search').value,list=searchListEpoch,opening=searchOpenEpoch;
    searchWriting=true;searchWriteControls(true);
    const owns=()=>!searchDeparted&&life===searchLife&&chosen===$('saved-search').value&&list===searchListEpoch&&opening===searchOpenEpoch;
    try {await fn(owns);} catch(error) {if(owns())searchStatus(error.message+(error.status&&error.status<500?'':' The write outcome may be unknown; inspect the saved-search list before repeating.'));}
    finally {if(life===searchLife){searchWriting=false;searchWriteControls(false);}}
  });
}
function searchWriteControls(disabled) { for(const id of ['save-search','rename-search','delete-search'])$(id).disabled=disabled; }
searchWrite('save-search-form',async owns=>{
  const row=validateSearch(await api('searches',{name:$('search-name').value,criteria:searchEntered()}));
  if(!owns())return;searchStatus(`Saved “${row.name}”: entered dynamic criteria, with no fixed membership.`);await refreshSearches(row.id,()=>!searchDeparted);
},'submit');
searchWrite('rename-search-form',async owns=>{
  const row=savedSearches.get($('saved-search').value);if(!row)throw Error('Choose a saved search.');
  const result=validateSearch(await api('searches/'+row.id+'/rename',{revision:row.revision,name:$('search-rename').value}),row.id);
  if(!owns())return;searchStatus(`Renamed to “${result.name}”. Criteria are unchanged.`);await refreshSearches(result.id,()=>!searchDeparted);
},'submit');
searchWrite('delete-search',async owns=>{
  const row=savedSearches.get($('saved-search').value);if(!row)throw Error('Choose a saved search.');
  if(!confirm(`Delete saved search “${row.name}”? Collection records and fixed selections are retained.`))return;
  const result=await api('searches/'+row.id+'/delete',{revision:row.revision});
  if(!owns())return;if(!searchKeys(result,['deleted'])||result.deleted!==row.id)throw Error('Invalid deletion receipt.');
  searchStatus('Saved search deleted. Collection and fixed selections are retained.');await refreshSearches('',()=>!searchDeparted);
});
$('open-search').addEventListener('click',e=>{e.preventDefault();openSearch();});
$('cancel-search-open').addEventListener('click',()=>cancelSearchOpen());
$('saved-search').addEventListener('change',()=>{++searchListEpoch;cancelSearchOpen('Choose Open dynamic search to apply these criteria.');});
$('refresh-searches').addEventListener('click',async()=>{cancelSearchOpen(null);const life=searchLife;try{await refreshSearches();}catch(error){if(!searchDeparted&&life===searchLife)searchStatus(error.message);}});
for(const event of ['input','change','submit'])$('filters').addEventListener(event,()=>{++searchFilterIntent;cancelSearchOpen(null);});
window.addEventListener('popstate',()=>{++searchFilterIntent;cancelSearchOpen(null);});
window.addEventListener('pagehide',()=>{searchDeparted=true;++searchLife;++searchListEpoch;cancelSearchOpen(null);searchWriting=false;searchWriteControls(false);});
window.addEventListener('pageshow',event=>{if(event.persisted){searchDeparted=false;refreshSearches().catch(error=>{if(!searchDeparted)searchStatus(error.message);});}});
refreshSearches().catch(error=>{if(!searchDeparted)searchStatus(error.message);});
