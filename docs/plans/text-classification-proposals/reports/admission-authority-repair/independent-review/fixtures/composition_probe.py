"""Read-only composition and static HTTP checks; never calls a model endpoint."""
import collections
import hashlib
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import urllib.request

ROOT = Path(__file__).resolve().parents[7]
sys.path.insert(0, str(ROOT))
from app import Dataset, make_handler

class Document(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids=[]; self.forms=[]; self.nested=[]; self.form_stack=[]; self.panel_forms={}; self.scripts=[]
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id']); self.panel_forms[attrs['id']]=list(self.form_stack)
        if tag=='form':
            self.forms.append(attrs.get('id'))
            if self.form_stack:self.nested.append((list(self.form_stack),attrs.get('id')))
            self.form_stack.append(attrs.get('id'))
        if tag=='script':self.scripts.append(attrs.get('src'))
    def handle_endtag(self, tag):
        if tag=='form':
            assert self.form_stack, 'Unmatched form end'
            self.form_stack.pop()

html=(ROOT/'static/workbench.html').read_bytes(); parsed=Document();parsed.feed(html.decode())
duplicates=[name for name,count in collections.Counter(parsed.ids).items() if count>1]
assert not duplicates, duplicates
assert not parsed.nested, parsed.nested
assert not parsed.form_stack
for panel in ('caption-proposal-panel','text-classification-proposal-panel'):
    assert parsed.panel_forms[panel]==[], (panel,parsed.panel_forms[panel])
for form in ('caption-proposal-form','text-classification-proposal-form'):
    assert parsed.forms.count(form)==1
assert parsed.scripts.count('/caption-proposals.js')==1
assert parsed.scripts.count('/text-classification-proposals.js')==1
assert parsed.scripts.index('/workbench.js')<parsed.scripts.index('/caption-proposals.js')<parsed.scripts.index('/text-classification-proposals.js')
http_results=[]
with tempfile.TemporaryDirectory(prefix='classification-composition-read-') as folder:
    data=Dataset(folder);server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(data))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        for url in ('/workbench','/workbench.js','/caption-proposals.js','/text-classification-proposals.js'):
            with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}'+url,timeout=3) as response:
                content=response.read();assert response.status==200
                local=ROOT/'static'/('workbench.html' if url=='/workbench' else url[1:])
                assert content==local.read_bytes()
                http_results.append({'path':url,'status':response.status,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()})
    finally:
        server.shutdown();server.server_close();data.close();thread.join(3)
files=['app.py','static/workbench.html','static/workbench.js','static/caption-proposals.js','static/text-classification-proposals.js','tests/browser_text_classification_proposals.cjs','tests/test_text_classification_proposals_controller.cjs']
print(json.dumps({'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    'ids':len(parsed.ids),'forms':parsed.forms,'duplicate_ids':duplicates,'nested_forms':parsed.nested,
    'panel_form_ancestors':{key:parsed.panel_forms[key] for key in ('caption-proposal-panel','text-classification-proposal-panel')},
    'scripts':parsed.scripts,'http':http_results,'files':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
    'real_model_calls':0},indent=2))
