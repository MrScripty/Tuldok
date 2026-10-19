'use strict';
// The project detail endpoint owns observations; this view owns one polling lifetime.
window.WorkspaceProjectActivity=function({read,onDetail}) {
  const esc=value=>window.workspaceEscape(value);
  let epoch=0,timer=null,request=null,deadline=null,root=null,previous=null,recent=[];
  function stop(){
    epoch++;clearTimeout(timer);clearTimeout(deadline);timer=null;deadline=null;
    request?.abort();request=null;root=null;
  }
  function paint(value,error='') {
    if(!root)return;
    const panel=root.querySelector('.project-live-activity'),activity=value?.activity;
    if(error||!activity?.available){
      panel.innerHTML=`<h3>Live project</h3><p role="status">${esc(error||activity?.reason||'Activity unavailable')}</p><small>Current progress is unavailable. Project references remain inspectable.</small>`;
      return;
    }
    const progress=activity.progress,total=progress.total;
    panel.innerHTML=`<h3>Live project · ${esc(activity.phase)}</h3><p role="status">${esc(activity.message)}</p><p><strong>${esc(activity.stale?'Waiting for producer':activity.state)}</strong> · ${esc(activity.producer)} · ${esc(activity.updated_at)}</p>${total!==null?`<progress value="${esc(progress.completed)}" max="${esc(Math.max(1,total))}" aria-label="Project progress"></progress><p>${esc(progress.completed)} / ${esc(total)}</p>`:`<p>${esc(progress.completed)} completed · total not yet known</p>`}${recent.length?`<p>Recently changed: ${recent.map(esc).join(', ')}</p>`:''}<small>External project activity. Managed execution and verified artifacts retain their own Run records.</small>`;
  }
  function start(value,target){
    stop();if(!value.activity)return;
    root=target;previous=value;recent=[];
    const panel=document.createElement('section');panel.className='panel panel-pad project-live-activity';
    root.querySelector('.project-header').after(panel);paint(value);
    const current=epoch,id=value.id;
    async function poll(){
      if(current!==epoch)return;
      if(!document.hidden){
        const pending=new AbortController();request=pending;
        deadline=setTimeout(()=>pending.abort(),10000);
        try{
          const next=await read(id,pending.signal);
          if(current!==epoch)return;
          if(next.id!==id||next.mode!=='inspection'||next.execution!=='unsupported'||!['data','recipes','evidence','requirements'].every(key=>Array.isArray(next[key])))throw Error('Unsupported project observation.');
          for(const group of ['data','recipes','evidence'])for(const ref of next[group]){
            const before=previous[group].find(old=>old.id===ref.id);
            if(before&&before.observed_sha256!==ref.observed_sha256)recent=[ref.label,...recent.filter(label=>label!==ref.label)].slice(0,5);
          }
          previous=next;paint(next);onDetail(next);
        }catch(error){if(current===epoch)paint(null,error.name==='AbortError'?'Project refresh timed out.':'Project refresh unavailable: '+error.message);}
        finally{if(current===epoch){clearTimeout(deadline);deadline=null;request=null;}}
      }
      if(current===epoch)timer=setTimeout(poll,1000);
    }
    timer=setTimeout(poll,1000);
  }
  return {start,stop};
};
