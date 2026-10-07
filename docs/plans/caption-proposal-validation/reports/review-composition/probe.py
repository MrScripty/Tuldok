import sys,json,unicodedata,itertools
from pathlib import Path
root=Path('/workspace/Tuldok-caption-validation-local')
sys.path.insert(0,str(root))
import ai_http
from workbench import text_value,IDENTIFIER
base=dict(source_id='a'*32,revision=2,source_revision=1,server_url='http://127.0.0.1:8765',model='fixture',instruction='Original exact guidance',seed=42,request_id='0'*31+'1')
cases=[]
def add(label,**change):
 b=dict(base,**change)
 try:
  assert set(b)==set(base)
  for k in ['source_id','request_id']:assert isinstance(b[k],str) and IDENTIFIER.fullmatch(b[k])
  for k in ['revision','source_revision']:assert type(b[k]) is int and b[k]>=1
  assert type(b['seed'])is int and 0<=b['seed']<=2**32-1
  text_value(ai_http.validate_url('llamacpp',b['server_url']),'Server URL',2048)
  text_value(ai_http.validate_model(b['model']),'Model ID',200)
  text_value(b['instruction'],'Caption guidance',2000)
  accepted=True;error=''
 except (ValueError,AssertionError,TypeError) as exc:accepted=False;error=str(exc)
 cases.append(dict(label=label,body=b,backend_accepted=accepted,backend_error=error))
whitespace=[chr(n) for n in range(0x110000) if chr(n).isspace()]
for c in whitespace+['\ufeff','\u180e','\u200b']:
 for k in ['model','instruction']:
  for value in [c,c*2,c+'Visible'+c,'Visible'+c+'Inside']:
   add(f'{k}:whitespace:{ord(c):04x}:{len(value)}',**{k:value})
 for pos in [' '+c+'http://host'+c+' ','http://ho'+c+'st/path','http://host/a'+c+'b']:
  add(f'url:whitespace:{ord(c):04x}',server_url=pos)
for n in range(0xD800,0xE000):
 for k in ['model','instruction','server_url']:
  add(f'{k}:surrogate:{n:04x}',**{k:('http://host/' if k=='server_url' else 'Visible')+chr(n)})
for n in range(32):
 for k in ['model','instruction','server_url']:
  add(f'{k}:control:{n}',**{k:('http://host/a' if k=='server_url' else 'Visible')+chr(n)+'b'})
for maximum,k,prefix in [(200,'model',''),(2000,'instruction',''),(2048,'server_url','HTTP://host/')]:
 for char in ['a','\U0001f600','\u00e9','\u200b']:
  for delta in [-1,0,1]:
   value=prefix+char*(maximum-len(prefix)+delta)
   for suffix in (['','/v1','/v1///','////','?','#','?a','#a'] if k=='server_url' else ['',' ','\u0085']):
    add(f'{k}:length:{maximum}:{delta}:{ord(char):04x}:{suffix}',**{k:value+suffix})
ports=['',':',':0',':00000',':1',':80',':443',':65535',':65536',':999999999999999999999999',':+80',':-80',':0x50',':\u0661',':80:80',':80foo']
hosts=['localhost','host','127.0.0.1','127.1','0x7f000001','[::1]','[::ffff:127.0.0.1]','[v1.test]','[::1]a','[::1].','[::1]:','[]','[127.0.0.1]','[:::1]','[::1','::1','host\\other','host%40x','host%2Fx','host%3Ax','host\x7f','\ufeffhost','host\ufeff','ho\uff1ast','ho\uff0fst','ho\uff20st','ho\uff1fst','ho\uff03st','\u0130host','\u212ahost']
for scheme,host,port,suffix in itertools.product(['http://','https://','HTTP://'],hosts,ports,['','/v1','/path','?','#']):
 add('url:authority',server_url=scheme+host+port+suffix)
for raw in ['http:///host','http:////host','http:/host','http:host','http:\\host','http:/\\host','http://@host','http://:@host','http://user:@host','http://:pass@host','http://host@','http://host@@other',' http://host ','http://host/\\path','http://host/?#','http://host/path?','http://host/path#']:
 add('url:syntax',server_url=raw)
# Check every Unicode code point whose NFKC form adds a URL delimiter.
for n in range(0x110000):
 c=chr(n)
 if any(d in unicodedata.normalize('NFKC',c) for d in '/?#@:') and c not in '/?#@:':
  add(f'url:nfkc:{n:04x}',server_url='http://a'+c+'b/path')
for k in ['model','instruction','server_url']:
 for value in [None,False,True,0,[],{}]:add(f'{k}:type',**{k:value})
for k in ['source_id','request_id']:
 for value in ['', 'a'*31, 'a'*33,'A'*32,'a'*32+'\n',True,None]:add(f'{k}:identifier',**{k:value})
for k in ['revision','source_revision']:
 for value in [True,False,0,-1,1.5,'1',None,1,9007199254740991,9007199254740992]:add(f'{k}:integer',**{k:value})
for value in [True,False,-1,0,1,1.5,4294967295,4294967296,'1',None]:add('seed:integer',seed=value)
Path('/workspace/tuldok-owner-review/caption-validation-local/review-composition/cases.json').write_text(json.dumps(cases,ensure_ascii=True))
print('Generated',len(cases),'independent cases;',len(whitespace),'Python whitespace characters')
