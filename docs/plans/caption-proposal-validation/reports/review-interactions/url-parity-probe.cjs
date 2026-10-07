const fs=require('node:fs'),vm=require('node:vm'),cp=require('node:child_process');
const root='/workspace/Tuldok-caption-validation-local';
const source=fs.readFileSync(root+'/static/caption-proposals.js','utf8').split('function captionProposalStoredRequest()',1)[0];
const context=vm.createContext({URL});vm.runInContext(source,context);
const cases=new Set();
const hosts=['host','localhost','127.0.0.1','127.1','0x7f000001','0','0127.0.0.1','256.0.0.1','host:','host:0','host:00001','host:65535','host:65536','host:-1','host:+1','host:1.0','host:1e1','host:٠١','host:１２','host:0x10','host:NaN','host:Infinity','host:80:81',':80','@host',':@host','host@','user@host','host\\other','host\\:80','host%40x','host%3ax','host%2fx','ho%00st','host%','host%FF','[::1]','[::1]:','[::1]:0','[::1]:80','[::1]x','[::1]x:80','[::1]:80:90','[127.0.0.1]','[v1.abc]','[::ffff:127.0.0.1]','[::1%25zone]','[::1%zone]','[[::1]]','[::1','::1]','é','ＦＯＯ','ho：st','ho／st','ho？st','ho＃st','ho＠st','ho℀st','ho℁st','ho℅st','host\u007f','host\u0085','host\ufeff','host\ud800'];
const paths=['','/','/v1','/v1///','/abc','/a\\b','/?','#','/?#','/?x','/#x','/a%20b','/a%00b','/a%FFb','/a\u007fb','/a\u0085b','/a\ufeffb','/a\ud800b'];
for(const host of hosts)for(const path of paths)cases.add('http://'+host+path);
for(const scheme of ['HTTP','HtTp','https','HTTPS','http:','http','ftp',''])for(const sep of ['://',':/',':///',':\\\\',':'])cases.add(scheme+sep+'host/v1');
const candidates=[...cases];
const py=cp.spawnSync('python',['-c',`import json,sys,ai_http\nfrom workbench import text_value\na=[]\nfor v in json.load(sys.stdin):\n try:\n  text_value(ai_http.validate_url('llamacpp',v),'URL',2048); a.append(True)\n except (ValueError,TypeError):a.append(False)\njson.dump(a,sys.stdout)`],{cwd:root,input:JSON.stringify(candidates),encoding:'utf8'});
if(py.status!==0)throw Error(py.stderr);const python=JSON.parse(py.stdout),mismatches=[];
for(const [i,url] of candidates.entries()){context.probe=url;let javascript=true;try{vm.runInContext('captionProposalServerURL(probe)',context);}catch{javascript=false;}if(javascript!==python[i])mismatches.push({url,javascript,python:python[i]});}
console.log(JSON.stringify({source_head:cp.execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),count:candidates.length,accepted_frontend_rejected_backend:mismatches.filter(x=>x.javascript&&!x.python),conservative_frontend_rejections:mismatches.filter(x=>!x.javascript&&x.python)},null,2));
