'use strict';
// Reused generic serial transaction fixture from the frozen controller suite;
// models IDB request queues/isolated snapshots/commit/abort, not admission logic.
const assert=require('node:assert/strict');
function atomicIndexedDB() {
  const data=new Map(),stores=new Set(),fault={open:false,get:false,put:false,delete:false,commit:false,transaction:false},history=[],heldCommits=[];
  let transactionTail=Promise.resolve(),holdCommit=false;
  const factory={data,fault,history,heldCommits,set holdCommit(value){holdCommit=value;},get holdCommit(){return holdCommit;},open(name,version){
    const request={};queueMicrotask(()=>{
      if(fault.open){request.onerror?.({preventDefault(){}});return;}
      let closed=false;
      const database={objectStoreNames:{contains:key=>stores.has(key)},createObjectStore:key=>{stores.add(key);},close(){closed=true;},transaction(storeName,mode,options){
        assert.equal(mode,'readwrite');assert.equal(options?.durability,'strict');if(closed||fault.transaction)throw Error('Synthetic transaction failure');
        const operations=[],transaction={oncomplete:null,onabort:null,onerror:null,error:null};let active=false,finished=false,working,release;
        const entry={mode,durability:options.durability,requests:[],committed:false,aborted:false};history.push(entry);
        const ready=transactionTail;transactionTail=new Promise(resolve=>release=resolve);
        function abort(){if(finished)return;finished=true;entry.aborted=true;queueMicrotask(()=>{transaction.onabort?.({preventDefault(){}});release();});}
        transaction.abort=abort;
        const store={};
        for(const operation of ['get','put','delete'])store[operation]=(...args)=>{
          if(finished)throw Error('Inactive transaction');const req={};operations.push({operation,args,req});entry.requests.push(operation);if(active)queueMicrotask(pump);return req;
        };
        transaction.objectStore=key=>{assert.equal(key,storeName);return store;};
        let pumping=false,commitQueued=false;
        function commit(){if(finished)return;if(fault.commit){abort();return;}finished=true;data.clear();for(const [key,value] of working)data.set(key,structuredClone(value));entry.committed=true;transaction.oncomplete?.({preventDefault(){}});release();}
        function pump(){
          if(!active||finished||pumping)return;pumping=true;
          const next=operations.shift();
          if(!next){pumping=false;if(!commitQueued){commitQueued=true;if(holdCommit)heldCommits.push(commit);else queueMicrotask(commit);}return;}
          const {operation,args,req}=next;
          if(fault[operation]){req.error=Error('Synthetic '+operation+' failure');const event={defaultPrevented:false,preventDefault(){this.defaultPrevented=true;}};req.onerror?.(event);transaction.onerror?.(event);if(!event.defaultPrevented)abort();pumping=false;if(!finished)queueMicrotask(pump);return;}
          if(operation==='get')req.result=structuredClone(working.get(args[0]));
          else if(operation==='put')working.set(args[1],structuredClone(args[0]));
          else working.delete(args[0]);
          try {req.onsuccess?.({preventDefault(){}});} catch(error){transaction.error=error;abort();}
          pumping=false;queueMicrotask(pump);
        }
        ready.then(()=>{if(finished)return;active=true;working=new Map([...data].map(([key,value])=>[key,structuredClone(value)]));pump();});
        return transaction;
      }};
      request.result=database;if(!stores.has('recovery'))request.onupgradeneeded?.({});request.onsuccess?.({});
    });return request;
  }};
  return factory;
}

module.exports={atomicIndexedDB};
