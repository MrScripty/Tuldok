"""Read-only selected serving alias/profile; no owner or inference admission."""
import http.client
import hashlib
import json
import time
import pumas_operations as typed

MAX_ALIASES = 64
MAX_REQUEST = 8192
SECONDS = 6
# Exact options used by the existing proposal owners, not producer-wide limits.
PURPOSES = {'classification': 2000, 'rewrite': 6000}

def catalog(base, deadline=None):
    try:result = typed.models(base, deadline=deadline)
    except (ValueError,OSError,http.client.HTTPException) as error:
        raise typed.OperationError('Serving catalog unavailable: '+(str(error) or 'bounded read failed')) from None
    if len(result['models']) > MAX_ALIASES:
        raise ValueError('Serving catalog exceeds64 aliases; pagination is unsupported.')
    return dict(result, catalog_projection_sha256=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),
                producer_contract_source=typed.SOURCE_COMMIT,
                scope='Serving alias observation; no local model-reference mapping, owner or inference admission.')

def selection(body, deadline=None):
    typed.object_fields(body,('server_url','model','profile','purpose'))
    if type(body['purpose']) is not str or body['purpose'] not in PURPOSES:
        raise ValueError('Only typed text classification/rewrite selection is supported; Image-to-Text and audio unavailable.')
    deadline = deadline if deadline is not None else time.monotonic()+SECONDS
    base=typed.endpoint(body['server_url']);model=typed.alias(body['model']);profile=typed.profile(body['profile'])
    listed=catalog(base,deadline)
    if model not in [row['id'] for row in listed['models']]:
        raise ValueError('Selected serving alias is absent; no local model ID or alternate alias fallback.')
    observed=typed.capabilities(base,model,profile,deadline=deadline)
    typed.require(observed,'chat_generation','messages_text','text',{'max_tokens':PURPOSES[body['purpose']]})
    if time.monotonic()>=deadline:raise ValueError('Selected model observation exceeded its bounded deadline.')
    return {'server_url':base,'model':model,'profile':observed['capabilities']['profile'],
            'protocol':typed.PROTOCOL,'purpose':body['purpose'],'capability_observation':observed,
            'catalog_projection_sha256':listed['catalog_projection_sha256'],
            'producer_contract_source':typed.SOURCE_COMMIT,'inference_admitted':False,
            'owner_authenticated':False,'scope':'Standalone selected text alias/exact profile configuration; generation separately revalidates capabilities. No owner authentication or lease.'}
