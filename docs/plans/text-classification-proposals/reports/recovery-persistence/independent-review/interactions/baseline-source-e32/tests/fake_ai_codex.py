import json
import sys
from pathlib import Path
from fake_ai import RESULT

def send(value):print(json.dumps(value),flush=True)
for line in sys.stdin:
    request=json.loads(line);method=request.get('method');params=request.get('params',{})
    if method=='initialize':
        assert params['clientInfo']['name']=='tuldok'
        send({'id':request['id'],'result':{}})
    elif method=='thread/start':
        assert params['sandbox']=='read-only' and params['ephemeral'] and params['approvalPolicy']=='never'
        assert 'Locate book corners' in params['developerInstructions']
        model=params['model']
        send({'id':request['id'],'result':{'thread':{'id':'test-thread'}}})
    elif method=='turn/start':
        assert params['outputSchema']['properties']['corner_reference']['enum']==['image']
        assert params['input'][1]['type']=='localImage'
        assert Path(params['input'][1]['path']).read_bytes().startswith(b'\xff\xd8')
        send({'id':request['id'],'result':{}})
        if model=='tools':
            send({'id':500,'method':'item/commandExecution/requestApproval','params':{}})
            continue
        text=json.dumps(dict(RESULT,corner_reference='image',book_top_left='top_left'))
        send({'method':'item/agentMessage/delta','params':{'threadId':'test-thread','itemId':'answer','delta':text}})
        send({'method':'turn/completed','params':{'threadId':'test-thread','turn':{'status':'completed','items':[{'type':'agentMessage','text':text}]}}})
