const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('static/caption-proposals.js','utf8');
const context=vm.createContext({URL,JSON,sessionStorage:{getItem:()=>null},$:()=>({disabled:false,textContent:''})});
vm.runInContext(source.slice(0,source.indexOf('const captionProposalActive')),context);
const base={source_id:'a'.repeat(32),request_id:'b'.repeat(32),revision:1,source_revision:1,server_url:'http://127.0.0.1:8000/',model:'fixture',instruction:'guide',seed:42};
const cases=[['ordinary',{}],['http_missing_slashes',{server_url:'http:127.0.0.1:8000'}],['http_single_slash',{server_url:'http:/127.0.0.1:8000'}],['http_backslashes',{server_url:String.raw`http:\\127.0.0.1:8000`}],['internal_NEL',{server_url:base.server_url+'a\u0085b'}],['port0',{server_url:'http://127.0.0.1:0/'}],['bom_prefix',{server_url:'\ufeff'+base.server_url}],['url_surrogate',{server_url:base.server_url+'\ud800'}],['empty_model',{model:''}],['model_surrogate',{model:'a\ud800'}],['empty_instruction',{instruction:''}],['instruction_surrogate',{instruction:'a\ud800'}]];
const result=cases.map(([name,patch])=>{context.body={...base,...patch};let accepted=true,error;try{vm.runInContext('captionProposalRecoveryBody(body)',context);}catch(e){accepted=false;error=e.message;}return {name,body:context.body,frontend_accepted:accepted,frontend_error:error};});
console.log(JSON.stringify(result,null,2));
