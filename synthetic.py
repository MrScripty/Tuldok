"""Persistent synthetic dataset jobs; one worker owns sequential Pumas requests."""
import json
import copy
import hashlib
from access import AccessError, authorized
import threading
import time
import uuid

import ai_http
import image_generation
import pumas_operations as pumas

BATCH_SIZE = 10
ACTIVE = ('preparing', 'generating', 'stopping')
# PR3 persisted only these exact size strings; they are not a current API field.
LEGACY_SIZES = {f'{width}x{height}' for width in (512, 768, 1024) for height in (512, 768, 1024)}


def saved_dimensions(value):
    """Decode retained dimensions without the new-request defaults or lost evidence."""
    if not isinstance(value, dict):
        raise ValueError('Saved image dimensions must be an object.')
    legacy = None
    if 'size' in value:
        size = value['size']
        if not isinstance(size, str) or size not in LEGACY_SIZES:
            raise ValueError('Unsupported saved image size: width and height must each be 512, 768, or 1024.')
        legacy = dict(zip(('width', 'height'), map(int, size.split('x'))))
    if 'width' in value or 'height' in value:
        dimensions = image_generation.validate_dimensions(value.get('width'), value.get('height'))
        if legacy is not None and dimensions != legacy:
            raise ValueError('Saved numeric dimensions conflict with the retained image size.')
    elif legacy is not None:
        dimensions = legacy
    else:
        raise ValueError('Saved image dimensions are missing; refusing to choose new-request defaults.')
    return dict(value, **dimensions)


def validate_saved_queue(job, entries):
    """Pure retained geometry policy shared by live recovery and inert history."""
    config = saved_dimensions(job['config'])
    normalized = [saved_dimensions(entry) for entry in entries]
    if any((entry['width'], entry['height']) != (config['width'], config['height']) for entry in normalized):
        raise ValueError('Saved queue-entry dimensions conflict with the job configuration.')
    return config, normalized


def validate_retained_attempt(job, entry, evidence):
    """Validate a retained typed request against its original queue intent.

    Capability observations are already decoded values. This policy consumes
    those historical values without discovering a server or admitting work.
    """
    config = job['config']
    if not pumas.typed(config):
        raise ValueError('Typed image evidence requires a typed image job.')
    observed = evidence['capability_observation']
    checked = pumas.validate_manifest(json.dumps(observed['capabilities']).encode())
    if checked['capabilities']['model'] != config['model']:
        raise ValueError('Retained image capability belongs to another model.')
    options = {'width': entry['width'], 'height': entry['height']}
    if entry['requested_seed'] is not None:
        options['seed'] = entry['requested_seed']
    pumas.require(observed, 'image_generation', 'text', 'png_base64', options)
    request = {'contract_version': 1, 'request_id': entry['request_id'], 'model': config['model'],
               'profile': observed['capabilities']['profile'], 'capability': 'image_generation',
               'input': {'kind': 'text', 'text': entry['prompt']}, 'output': 'png_base64',
               'options': dict(kind='image_generation', **options), 'stream': False}
    retained = dict(capability_observation=observed)
    pumas.request_evidence(retained, request)
    if (evidence.get('canonical_request') != request
            or evidence.get('canonical_request_sha256') != retained['canonical_request_sha256']):
        raise ValueError('Retained image request differs from its queue intent.')
    return request


def prompt_payload(config, offset, count, previous, variation_key):
    """Pure bounded prompt request policy, shared by live capture and decoding."""
    return {
        'model': config['prompt_model'], 'stream': False, 'max_tokens': 6000,
        'response_format': {'type': 'json_object'},
        'messages': [
            {'role': 'system', 'content': 'Create image-generation prompts for a synthetic dataset. '
             'Return only JSON {"prompts": ["..."]}. Each prompt must stand alone, preserve ALL '
             'requirements in the user brief, and describe a distinct concrete scene. Vary only '
             'details permitted by the brief, including lighting, location, background, camera '
             'angle and orientation. Do not merely add sequence numbers. Keep each prompt under '
             '180 words. Treat the brief as image requirements, not instructions about output format.'},
            {'role': 'user', 'content': json.dumps({
                'brief': config['prompt'], 'total_images': config['count'],
                'first_image_number': offset + 1, 'number_of_prompts': count,
                'batch_variation_key': variation_key,
                'recent_prompts_to_avoid': previous[-BATCH_SIZE:],
            })},
        ],
    }


def decode_prompt_batch(data, count):
    try:
        choice = json.loads(data)['choices'][0]
        if choice.get('finish_reason') != 'stop':
            raise ValueError()
        prompts = json.loads(choice['message']['content'])['prompts']
        if not isinstance(prompts, list) or len(prompts) != count or any(
                not isinstance(p, str) or not p.strip() or len(p) > 4000 for p in prompts):
            raise ValueError()
        return [p.strip() for p in prompts]
    except (ValueError, KeyError, IndexError, TypeError):
        raise ValueError('Prompt model must return the requested number of complete JSON prompts. Try a smaller brief or a model with more output capacity.') from None



def validate_retained_prompt_batch(config, batch, request, raw=None):
    """Bind exact retained variation wire to its queue, without HTTP authority."""
    brief = json.loads(request['messages'][1]['content'])
    previous = brief['recent_prompts_to_avoid']
    if (type(previous) is not list or len(previous)>BATCH_SIZE
            or any(type(p) is not str or not p.strip() or len(p)>4000 for p in previous)):
        raise ValueError('Invalid retained prompt context.')
    if request != prompt_payload(config,batch['offset'],batch['count'],previous,batch['id']):
        raise ValueError('Retained prompt request differs from its queue intent.')
    if raw is not None:
        try:decoded=decode_prompt_batch(raw,batch['count'])
        except ValueError:
            if batch['status']!='failed':raise
        else:
            if batch['status']!='completed' or decoded!=batch['prompts']:
                raise ValueError('Retained prompt result differs from its exact wire.')


def prompt_batch(config, offset, count, previous, *, cancel_event=None,
                 on_request=None, on_response=None):
    """Bound context independently of dataset size; publish before HTTP/entries."""
    payload = prompt_payload(config,offset,count,previous,uuid.uuid4().hex)
    if on_request is not None:on_request(payload)

    with ai_http.request(config['prompt_url'], '/v1/chat/completions', payload,
                         timeout=180, label='Pumas prompt model', cancel_event=cancel_event) as (response, transport, deadline):
        data = bytearray()
        while not response.isclosed():
            transport.settimeout(max(.001, deadline - time.monotonic()))
            if time.monotonic() >= deadline:
                raise ValueError('Prompt generation timed out.')
            chunk = response.read1(65536)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > 256 * 1024:
                raise ValueError('Prompt model returned an oversized response.')
    try:
        prompts=decode_prompt_batch(data,count)
    except ValueError as error:
        if on_response is not None:on_response(payload,bytes(data),None,str(error))
        raise
    if on_response is not None:on_response(payload,bytes(data),prompts,'')
    return prompts


def validate(body):
    if 'size' in body:
        raise ValueError('size is no longer supported for new jobs; use numeric width and height.')
    count = body.get('count')
    if type(count) is not int or not 1 <= count <= 10000:
        raise ValueError('Choose 1 to 10,000 images.')
    strategy = body.get('strategy')
    if strategy not in ('varied', 'repeat'):
        raise ValueError('Choose varied prompts or repeat the same prompt.')
    image = {key: body[key] for key in ('server_url', 'model', 'prompt', 'width', 'height', 'seed', 'protocol', 'profile') if key in body}
    base, _, payload = image_generation.validate(dict(image, request_id=uuid.uuid4().hex))
    config = dict(image, server_url=base, width=payload['width'], height=payload['height'], count=count, strategy=strategy)
    if pumas.typed(config) and strategy != 'repeat':
        raise ValueError('Typed image batches currently support repeat prompts. Select repeat explicitly.')
    if strategy == 'varied':
        config['prompt_url'] = ai_http.validate_url('llamacpp', body.get('prompt_url') or base)
        config['prompt_model'] = ai_http.validate_model(body.get('prompt_model'))
    return config


class Jobs:
    def __init__(self, dataset):
        self.dataset = dataset
        self.access = dataset.access
        self.lock = dataset.lock
        self.db = dataset.db
        self.worker = None
        self.stop = threading.Event()
        self.request_id = None
        with self.access._reconcile(), self.lock, self.db.transaction():
            self.runtime_owner = self.db.claim_runtime('generation_jobs')
            if not self.runtime_owner:
                return
            for job in self._jobs():
                try:
                    job = self._normalize_saved(job)
                except ValueError as error:
                    # An invalid retained queue must stay inspectable without
                    # stopping startup of independent datasets/jobs.
                    if job['status'] != 'completed':
                        job.update(status='failed', error=str(error))
                        self._save(job)
                    continue
                if job['status'] in ACTIVE:
                    job.update(status='interrupted', error='Server stopped. Resume to continue the saved queue.')
                    if pumas.typed(job['config']):
                        for entry in self._entries(job['id']):
                            if entry['status'] == 'generating':
                                entry.update(status='failed', provider_outcome='unknown',
                                    error='Server stopped during an image attempt; provider outcome unknown. No replay.')
                                self._entry(entry)
                        job['error'] = 'Server stopped. Inspect retained attempts; uncertain image work cannot replay.'
                    self._save(job)
                    self.access.audit('synthetic.reconcile', job['id'], {'status': job['status']})

    def _jobs(self):
        return [json.loads(r[0]) for r in self.db.execute('SELECT data FROM generation_jobs ORDER BY ordinal')]

    def _save(self, job):
        self.db.execute('INSERT INTO generation_jobs (id, data) VALUES (%s,%s) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (job['id'], json.dumps(job)))

        execution = getattr(self.dataset, 'project_execution', None)
        if execution is not None:
            execution.mark_generation(job['id'])

    def _entries(self, job_id):
        return [json.loads(r[0]) for r in self.db.execute('SELECT data FROM generation_entries WHERE job_id=%s ORDER BY ordinal', (job_id,))]

    def _entry(self, entry):
        self.db.execute('INSERT INTO generation_entries (id, job_id, ordinal, data) VALUES (%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                        (entry['id'], entry['job_id'], entry['ordinal'], json.dumps(entry)))

        execution = getattr(self.dataset, 'project_execution', None)
        if execution is not None:
            execution.mark_generation(entry['job_id'])

    def _normalize_saved(self, job):
        entries = self._entries(job['id'])
        config, normalized = validate_saved_queue(job, entries)
        # Decode the whole queue before writing, keeping migration atomic under
        # the caller's lock/transaction. Retain size and all original provenance.
        if config != job['config']:
            job = dict(job, config=config)
            self._save(job)
        for before, entry in zip(entries, normalized):
            if before != entry:
                self._entry(entry)
        return job

    def record_output(self, sample_id, entry, job, metadata):
        """Called only inside Dataset.add's sample-insert transaction and lock."""
        self.access.require_job('synthetic', job['id'], job.get('admission_id'), self._request_digest(job))
        self.access.require('edit', 'dataset.add_generated', job['id'])
        previous_entry, previous_job = dict(entry), dict(job)

        def restore_progress():
            entry.clear()
            entry.update(previous_entry)
            job.clear()
            job.update(previous_job)

        self.db.on_rollback(restore_progress)
        entry.update(status='completed', sample_id=sample_id, metadata=metadata)
        if pumas.typed(job['config']) or getattr(self.dataset,'project_execution',None) is not None: entry['provider_outcome'] = 'result_received'
        self._entry(entry)
        job['completed'] += 1
        self._save(job)

    @authorized('inspect', 'synthetic.snapshot')
    def snapshot(self):
        with self.lock:
            return {'jobs': self._jobs(), 'entries': [json.loads(r[0]) for r in self.db.execute('SELECT data FROM generation_entries ORDER BY storage_order')]}

    @authorized('execute', 'synthetic.start', owner_only=True)
    def start(self, body):
        with self.lock:
            if self.db.in_transaction:
                raise ValueError('Generation dispatch requires its own committed transaction.')
            with self.db.transaction():
                job, launch = self._prepare_start(body)
            if launch:
                self._launch(job)
        return job

    def _prepare_start(self, body):
        if not self.db.in_transaction:
            raise RuntimeError('Producer preparation requires an owned transaction.')
        from app import metadata
        config, meta = validate(body), metadata(body)
        self._idle()
        job = dict(id=uuid.uuid4().hex, config=config, meta=meta, status='preparing', error='', completed=0)
        self._admit(job, 'synthetic.start')
        self._save(job)
        return job, True

    def _idle(self):
        if not self.runtime_owner:
            raise ValueError('Generation workers belong to another open application. Use that application or reopen after it closes.')
        if self.worker and self.worker.is_alive():
            raise ValueError('A generation job is already running. Stop it before starting another.')
        if any(job['status'] in ACTIVE for job in self._jobs()):
            raise ValueError('A generation job is already starting.')

    @authorized('execute', 'synthetic.resume', owner_only=True)
    def resume(self, job_id):
        with self.lock:
            if self.db.in_transaction:
                raise ValueError('Generation dispatch requires its own committed transaction.')
            with self.db.transaction():
                job, launch = self._prepare_resume(job_id)
            if launch:
                self._launch(job)
        return job

    def _prepare_resume(self, job_id):
        if not self.db.in_transaction:
            raise RuntimeError('Producer preparation requires an owned transaction.')
        self._idle()
        job = next((j for j in self._jobs() if j['id'] == job_id), None)
        if not job or job['status'] == 'completed':
            raise ValueError('Choose an unfinished generation job.')
        job = self._normalize_saved(job)
        if (pumas.typed(job['config']) or getattr(self.dataset,'project_execution',None) is not None) and any(e.get('provider_outcome') == 'unknown' for e in self._entries(job_id)):
            raise ValueError('An image attempt has an unknown provider outcome. Inspect it; this queue cannot replay it.')
        job.update(status='preparing', error='')
        self._admit(job, 'synthetic.resume')
        self._save(job)
        return job, True

    @staticmethod
    def _request_digest(job):
        return hashlib.sha256(json.dumps({'config': job['config'], 'meta': job['meta']},
            sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

    def _admit(self, job, action):
        job['request_digest'] = self._request_digest(job)
        job['admission_id'] = self.access.admit_job('synthetic', job['id'], job['request_digest'],
            {'dataset.add_generated': [job['id']], 'images.generate_admitted': [job['id']], 'synthetic.finish': [job['id']]})
        self.access.audit(action, job['id'], {'request_digest': job['request_digest']})

    def _launch(self, job):
        self.stop.clear()
        self.worker = threading.Thread(target=self._run, args=(copy.deepcopy(job),), daemon=True)
        try:
            self.worker.start()
        except RuntimeError:
            self.worker = None
            with self.db.transaction():
                job.update(status='failed', error='Could not start the generation worker; no inference ran. Resume explicitly.')
                self._save(job)

    @authorized('cancel', 'synthetic.cancel')
    def cancel(self, job_id):
        with self.lock, self.db.transaction():
            result, pending = self._prepare_cancel(job_id)
            if pending is not None and self._signal_cancel(pending):
                self._cancel_transport(pending)
            return result

    def _prepare_cancel(self, job_id):
        """Persist intent only; project dispatch signals after canonical ACK."""
        if not self.db.in_transaction:
            raise RuntimeError('Producer cancellation preparation requires an owned transaction.')
        if not self.runtime_owner:
            raise ValueError('Generation workers belong to another open application. Cancel in that application.')
        job = next((j for j in self._jobs() if j['id'] == job_id), None)
        if not job or job['status'] not in ACTIVE:
            return {'cancelled': False}, None
        pending = (self.worker, job_id, self.request_id)
        job['status'] = 'stopping'
        self._save(job)
        self.access.audit('synthetic.cancel', job_id)
        return {'cancelled': True}, pending

    def _signal_cancel(self, pending):
        if self.worker is not pending[0]:
            return False
        self.stop.set()
        return True

    def _cancel_transport(self, pending):
        if pending[2]:
            self.dataset.image_requests.cancel(pending[2])

    def close(self):
        self.stop.set()
        if self.request_id:
            with self.access._reconcile():
                self.dataset.image_requests.cancel(self.request_id)
        if self.worker:
            self.worker.join()

    def _check(self):
        if self.stop.is_set():
            raise ValueError('Generation stopped. Resume to continue.')

    def _run(self, job):
        try:
            with self.access._job('synthetic', job['id'], job.get('admission_id'), self._request_digest(job)):
                self._run_admitted(job)
        except AccessError:
            with self.access._reconcile(), self.lock, self.db.transaction():
                job.update(status='interrupted', error='Job admission is missing or differs from the retained request; no inference started.')
                self._save(job)
                self.access.audit('synthetic.interrupt', job['id'])

    def _run_admitted(self, job):
        config = job['config']
        try:
            with self.lock:
                entries = self._entries(job['id'])
            if config['strategy'] == 'varied':
                seen = {' '.join(e['prompt'].casefold().split()) for e in entries}
                attempts = 0
                while len(entries) < config['count']:
                    self._check()
                    count = min(BATCH_SIZE, config['count'] - len(entries))
                    def retain_request(payload):
                        if getattr(self.dataset,'project_execution',None) is None:return
                        brief=json.loads(payload['messages'][1]['content'])
                        batch=dict(id=brief['batch_variation_key'],offset=len(entries),count=count,status='requesting',error='',
                                   request_sha256=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),
                                   response_sha256=None,prompts=None,canonical_request=payload,raw_response_base64=None)
                        with self.lock,self.db.transaction():
                            job.setdefault('prompt_batches',[]).append(batch)
                            self._save(job)
                    def retain_response(payload,raw,prompts,error):
                        if getattr(self.dataset,'project_execution',None) is None:return
                        import base64
                        with self.lock,self.db.transaction():
                            batch=job['prompt_batches'][-1]
                            batch.update(status='failed' if error else 'completed',error=error,prompts=prompts,
                                         raw_response_base64=base64.b64encode(raw).decode('ascii'),response_sha256=hashlib.sha256(raw).hexdigest())
                            self._save(job)
                    if getattr(self.dataset,'project_execution',None) is None:
                        prompts = prompt_batch(config,len(entries),count,[e['prompt'] for e in entries[-BATCH_SIZE:]])
                    else:
                        prompts = prompt_batch(config,len(entries),count,[e['prompt'] for e in entries[-BATCH_SIZE:]],
                                               cancel_event=self.stop,on_request=retain_request,on_response=retain_response)
                    self._check()
                    added = []
                    for prompt in prompts:
                        key = ' '.join(prompt.casefold().split())
                        if key not in seen:
                            seen.add(key)
                            added.append(self._new_entry(job, len(entries) + len(added), prompt))
                    with self.lock, self.db.transaction():
                        for entry in added:
                            self._entry(entry)
                    entries.extend(added)
                    attempts = 0 if len(added) == count else attempts + 1
                    if attempts >= 3:
                        raise ValueError('Prompt model repeatedly returned duplicates. Saved unique prompts; resume to fill the remaining slots.')
            job['status'] = 'generating'
            with self.lock, self.db.transaction():
                self._save(job)
            for ordinal in range(config['count']):
                self._check()
                if ordinal == len(entries):
                    entry = self._new_entry(job, ordinal, config['prompt'])
                    entries.append(entry)
                    with self.lock, self.db.transaction():
                        self._entry(entry)
                entry = entries[ordinal]
                if entry.get('sample_id') or entry['status'] == 'deleted':
                    continue
                entry.update(status='generating', error='')
                with self.lock, self.db.transaction():
                    self.request_id = uuid.uuid4().hex
                    if pumas.typed(config) or getattr(self.dataset,'project_execution',None) is not None:
                        entry.update(request_id=self.request_id, provider_outcome='unknown')
                    self._entry(entry)
                body = {key: config[key] for key in ('server_url', 'model', 'width', 'height')}
                body.update({key: config[key] for key in ('protocol', 'profile') if key in config})
                body.update(prompt=entry['prompt'], request_id=self.request_id)
                if config.get('seed') is not None:
                    body['seed'] = (config['seed'] + ordinal) % 4294967296
                self._check()
                def retain_admission(evidence):
                    validate_retained_attempt(job, entry, evidence)
                    with self.lock, self.db.transaction():
                        if self.stop.is_set():
                            raise pumas.OperationError('Cancelled before image provider admission.')
                        entry['attempt_evidence'] = evidence
                        self._entry(entry)
                result = self.dataset.image_requests._generate_admitted(body, job['id'], cancel_event=self.stop,
                    **({'on_admission': retain_admission} if pumas.typed(config) else {}))
                # Queue link and sample insert commit together, including across restarts.
                with self.lock:
                    self._check()
                    self.dataset.add(dict(job['meta'], image=result['image'],
                        filename=f'synthetic-{job["id"][:8]}-{ordinal + 1:05d}.png'),
                        generation=(entry, job, result['metadata']))
                with self.lock:
                    self.request_id = None
            job.update(status='completed', error='')
        except Exception as error:
            job.update(status='cancelled' if self.stop.is_set() else 'failed', error=str(error)[:800])
            pumas.failure_evidence(job, error)
            with self.lock, self.db.transaction():
                for entry in self._entries(job['id']):
                    if entry['status'] == 'generating':
                        if pumas.typed(config):
                            entry['provider_outcome'] = getattr(error, 'outcome', 'unknown')
                            entry['status'] = 'failed'
                            entry['error'] = job['error']
                            self._entry(entry)
                            continue
                        entry.update(status='pending' if self.stop.is_set() else 'failed', error=job['error'])
                        self._entry(entry)
        finally:
            with self.lock, self.db.transaction():
                self.request_id = None
                self._save(job)
                self.access.audit('synthetic.finish', job['id'], {'status': job['status'], 'completed': job['completed']})

    @staticmethod
    def _new_entry(job, ordinal, prompt):
        return dict(id=uuid.uuid4().hex, job_id=job['id'], ordinal=ordinal, prompt=prompt,
                    status='pending', sample_id=None, error='', model=job['config']['model'],
                    width=job['config']['width'], height=job['config']['height'], requested_seed=(job['config']['seed'] + ordinal) % 4294967296
                    if job['config'].get('seed') is not None else None)
