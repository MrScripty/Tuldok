"""Original SDK owner/IPC with controlled HTTP/index fixture; no inference runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pumas_owner_reuse as reuse

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bridge',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    fixture_root=out/'owned-fixture';fixture_root.mkdir()
    log=(out/'fixture.log').open('wb')
    process=subprocess.Popen([str(a.fixture.resolve()),str(fixture_root)],stdout=log,stderr=subprocess.STDOUT)
    checks=[];rows=[]
    try:
        ready=fixture_root/'ready.json';deadline=time.monotonic()+20
        while not ready.is_file():
            if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Owned original SDK fixture startup failed: '+(out/'fixture.log').read_text()[-4000:])
            time.sleep(.02)
        metadata=json.loads(ready.read_text());registry=Path(metadata['registry']);selected=metadata['selected']
        service=reuse.Service(a.bridge,registry,hashlib.sha256(a.bridge.read_bytes()).hexdigest())
        def state():
            with sqlite3.connect(registry) as db:return list(db.execute('SELECT * FROM instances'))
        before=state()
        libraries=service.libraries({});(out/'libraries.json').write_text(json.dumps(libraries,indent=2)+'\n')
        assert len(libraries['registered_libraries'])==3
        snapshots=[r for r in libraries['local_models'] if r['observation']=='snapshot']
        assert len(snapshots)==2 and len({r['library_root'] for r in snapshots})==2
        assert all(r['snapshot']['rows'][0]['model_id']=='same-model-id' for r in snapshots)
        assert any(r['observation']=='unavailable' for r in libraries['local_models'])
        checks.append('three registered contexts; two colliding local model IDs remain scoped; absent index unavailable')
        receipt=service.observe({'selected':selected});(out/'observation.json').write_text(json.dumps(receipt,indent=2)+'\n')
        used=service.use({'receipt':receipt,'protocol':'legacy'});assert used['observation']['service']==receipt['observation']['service']
        checks.append('actual authenticated original core IPC→HTTP descriptor→final core reauthentication; fresh Use equality')
        assert state()==before;checks.append('read-only listing and borrowed handle disposal preserve complete owner rows')
        def refused(action,phrase=None):
            try:action()
            except ValueError as e:
                if phrase:assert phrase in str(e)
                assert state()==before
                return str(e)
            raise AssertionError('Expected honest unsupported/unresolved refusal')
        rows.append(refused(lambda:service.use({'receipt':receipt,'protocol':'pumas_typed_v1'}),'separate producer stacks'))
        other=next(r for r in libraries['registered_libraries'] if r['name']=='other')
        rows.append(refused(lambda:service.observe({'selected':{'id':other['id'],'root':other['root']}})))
        checks.append('separate typed stack and ownerless registered library refused with no second owner')
        for mode in ['wrong-service','wrong-core']:
            (fixture_root/'mode').write_text(mode)
            rows.append(refused(lambda:service.observe({'selected':selected})))
        (fixture_root/'mode').write_text('')
        checks.append('impostor/stale HTTP service and core generations refused by original SDK, owner rows intact')
        with sqlite3.connect(registry) as db:
            original=db.execute('SELECT connection_token FROM instances WHERE library_path=?',(selected['root'],)).fetchone()[0]
            db.execute('UPDATE instances SET connection_token=? WHERE library_path=?',('wrong-credential',selected['root']))
        try:
            try:service.observe({'selected':selected})
            except ValueError:pass
            else:raise AssertionError('Unauthenticated advertisement accepted')
            with sqlite3.connect(registry) as db:assert db.execute('SELECT connection_token FROM instances WHERE library_path=?',(selected['root'],)).fetchone()[0]=='wrong-credential'
        finally:
            with sqlite3.connect(registry) as db:db.execute('UPDATE instances SET connection_token=? WHERE library_path=?',(original,selected['root']))
        assert state()==before;checks.append('wrong actual registry credential rejected, not reclaimed or overwritten')
        (fixture_root/'mode').write_text('hold')
        entered=fixture_root/'http-entered'
        failure=[]
        import threading
        def observe():
            try:service.observe({'selected':selected})
            except ValueError as e:failure.append(str(e))
        thread=threading.Thread(target=observe);thread.start()
        deadline=time.monotonic()+10
        while not entered.exists():
            if not thread.is_alive() or time.monotonic()>deadline:raise AssertionError('HTTP hold did not enter')
            time.sleep(.01)
        with sqlite3.connect(registry) as db:
            original_generation=db.execute('SELECT started_at FROM instances WHERE library_path=?',(selected['root'],)).fetchone()[0]
            db.execute('UPDATE instances SET started_at=? WHERE library_path=?',('controlled-successor-generation',selected['root']))
        (fixture_root/'mode').write_text('')
        thread.join(12);assert not thread.is_alive() and failure
        with sqlite3.connect(registry) as db:db.execute('UPDATE instances SET started_at=? WHERE library_path=?',(original_generation,selected['root']))
        assert state()==before;checks.append('owner generation change after HTTP observation fails final core authentication; no takeover')
        service.observe({'selected':selected});assert state()==before
        def index_action(action):
            completed=fixture_root/'index-completed';completed.unlink(missing_ok=True)
            (fixture_root/'index-command').write_text(action)
            deadline=time.monotonic()+10
            while not completed.exists():
                if process.poll() is not None or time.monotonic()>deadline:raise AssertionError('Owned original ModelIndex action failed')
                time.sleep(.01)
            assert completed.read_text()==action
        index_action('oversize')
        try:
            rows.append(refused(lambda:service.libraries({}),'incomplete/inconsistent'))
            checks.append('original SDK selector total_count65 with64 returned rows refuses truncation; original owner unchanged')
        finally:index_action('restore')
        restored=service.libraries({})
        assert all(r['snapshot']['total_count']==len(r['snapshot'].get('rows',[]))==1 for r in restored['local_models'] if r['observation']=='snapshot')
        requests=[json.loads(line)['request'] for line in (fixture_root/'requests.jsonl').read_text().splitlines()]
        assert all(r.startswith('GET /.well-known/pumas HTTP/') for r in requests)
        checks.append('only descriptor HTTP GETs; no models, inference, startup or acquisition requests')
        report={'result':'PASS','scope':metadata['scope'],'producer_head':reuse.SOURCE,'checks':checks,'refusals':rows,
                'bridge_sha256':service.bridge_sha256,'fixture_sha256':hashlib.sha256(a.fixture.read_bytes()).hexdigest(),
                'complete_owner_row_sha256_before_and_after':hashlib.sha256(reuse.canonical(before)).hexdigest(),
                'HTTP_requests':requests,'owner_rows_unchanged':True,'consumer_owner_startups':0,'original_packet_acceptance':False,
                'scientific_or_model_quality':False}
        (out/'native-qualification.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    finally:
        (fixture_root/'mode').write_text('');(fixture_root/'stop').write_text('stop')
        try:process.wait(timeout=20)
        except subprocess.TimeoutExpired:process.kill();process.wait();raise RuntimeError('Owned fixture teardown failed')
        log.close()
    shutdown=json.loads((fixture_root/'shutdown.json').read_text());assert shutdown['ordered_http_and_core_shutdown'] and shutdown['remaining_instances']==0
    assert process.returncode==0

if __name__=='__main__':main()
