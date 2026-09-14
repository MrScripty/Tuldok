"""Persistent synthetic dataset jobs; one worker owns sequential Pumas requests."""
import json
import threading
import time
import uuid

import ai_http
import image_generation

BATCH_SIZE = 10
ACTIVE = ('preparing', 'generating', 'stopping')


def prompt_batch(config, offset, count, previous):
    """Bound context independently of dataset size; uniqueness is checked locally."""
    payload = {
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
                'batch_variation_key': uuid.uuid4().hex,
                'recent_prompts_to_avoid': previous[-BATCH_SIZE:],
            })},
        ],
    }
    with ai_http.request(config['prompt_url'], '/v1/chat/completions', payload,
                         timeout=180, label='Pumas prompt model') as (response, transport, deadline):
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


def validate(body):
    count = body.get('count')
    if type(count) is not int or not 1 <= count <= 10000:
        raise ValueError('Choose 1 to 10,000 images.')
    strategy = body.get('strategy')
    if strategy not in ('varied', 'repeat'):
        raise ValueError('Choose varied prompts or repeat the same prompt.')
    image = {key: body[key] for key in ('server_url', 'model', 'prompt', 'size', 'seed') if key in body}
    base, _, payload = image_generation.validate(dict(image, request_id=uuid.uuid4().hex))
    config = dict(image, server_url=base, size=payload['size'], count=count, strategy=strategy)
    if strategy == 'varied':
        config['prompt_url'] = ai_http.validate_url('llamacpp', body.get('prompt_url') or base)
        config['prompt_model'] = ai_http.validate_model(body.get('prompt_model'))
    return config


class Jobs:
    def __init__(self, dataset):
        self.dataset = dataset
        self.lock = dataset.lock
        self.db = dataset.db
        self.worker = None
        self.stop = threading.Event()
        self.request_id = None
        with self.lock, self.db:
            self.db.execute('CREATE TABLE IF NOT EXISTS generation_jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS generation_entries (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, ordinal INTEGER NOT NULL, data TEXT NOT NULL, UNIQUE(job_id, ordinal))')
            for job in self._jobs():
                if job['status'] in ACTIVE:
                    job.update(status='interrupted', error='Server stopped. Resume to continue the saved queue.')
                    self._save(job)

    def _jobs(self):
        return [json.loads(r[0]) for r in self.db.execute('SELECT data FROM generation_jobs ORDER BY rowid')]

    def _save(self, job):
        self.db.execute('INSERT INTO generation_jobs VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (job['id'], json.dumps(job)))

    def _entries(self, job_id):
        return [json.loads(r[0]) for r in self.db.execute('SELECT data FROM generation_entries WHERE job_id=? ORDER BY ordinal', (job_id,))]

    def _entry(self, entry):
        self.db.execute('INSERT INTO generation_entries VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                        (entry['id'], entry['job_id'], entry['ordinal'], json.dumps(entry)))

    def record_output(self, sample_id, entry, job, metadata):
        """Called only inside Dataset.add's sample-insert transaction and lock."""
        entry.update(status='completed', sample_id=sample_id, metadata=metadata)
        self._entry(entry)
        job['completed'] += 1
        self._save(job)

    def snapshot(self):
        with self.lock:
            return {'jobs': self._jobs(), 'entries': [json.loads(r[0]) for r in self.db.execute('SELECT data FROM generation_entries ORDER BY rowid')]}

    def start(self, body):
        # Validate everything before starting billable work or persisting a job.
        from app import metadata
        config, meta = validate(body), metadata(body)
        with self.lock, self.db:
            self._idle()
            job = dict(id=uuid.uuid4().hex, config=config, meta=meta, status='preparing', error='', completed=0)
            self._save(job)
            self._launch(job)
        return job

    def _idle(self):
        if self.worker and self.worker.is_alive():
            raise ValueError('A generation job is already running. Stop it before starting another.')
        if any(job['status'] in ACTIVE for job in self._jobs()):
            raise ValueError('A generation job is already starting.')

    def resume(self, job_id):
        with self.lock, self.db:
            self._idle()
            job = next((j for j in self._jobs() if j['id'] == job_id), None)
            if not job or job['status'] == 'completed':
                raise ValueError('Choose an unfinished generation job.')
            job.update(status='preparing', error='')
            self._save(job)
            self._launch(job)
        return job

    def _launch(self, job):
        self.stop.clear()
        self.worker = threading.Thread(target=self._run, args=(job,), daemon=True)
        self.worker.start()

    def cancel(self, job_id):
        with self.lock, self.db:
            job = next((j for j in self._jobs() if j['id'] == job_id), None)
            if not job or job['status'] not in ACTIVE:
                return {'cancelled': False}
            self.stop.set()
            job['status'] = 'stopping'
            self._save(job)
            if self.request_id:
                self.dataset.image_requests.cancel(self.request_id)
        return {'cancelled': True}

    def close(self):
        self.stop.set()
        if self.request_id:
            self.dataset.image_requests.cancel(self.request_id)
        if self.worker:
            self.worker.join()

    def _check(self):
        if self.stop.is_set():
            raise ValueError('Generation stopped. Resume to continue.')

    def _run(self, job):
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
                    prompts = prompt_batch(config, len(entries), count, [e['prompt'] for e in entries[-BATCH_SIZE:]])
                    self._check()
                    added = []
                    for prompt in prompts:
                        key = ' '.join(prompt.casefold().split())
                        if key not in seen:
                            seen.add(key)
                            added.append(self._new_entry(job, len(entries) + len(added), prompt))
                    with self.lock, self.db:
                        for entry in added:
                            self._entry(entry)
                    entries.extend(added)
                    attempts = 0 if len(added) == count else attempts + 1
                    if attempts >= 3:
                        raise ValueError('Prompt model repeatedly returned duplicates. Saved unique prompts; resume to fill the remaining slots.')
            job['status'] = 'generating'
            with self.lock, self.db:
                self._save(job)
            for ordinal in range(config['count']):
                self._check()
                if ordinal == len(entries):
                    entry = self._new_entry(job, ordinal, config['prompt'])
                    entries.append(entry)
                    with self.lock, self.db:
                        self._entry(entry)
                entry = entries[ordinal]
                if entry.get('sample_id') or entry['status'] == 'deleted':
                    continue
                entry.update(status='generating', error='')
                with self.lock, self.db:
                    self._entry(entry)
                    self.request_id = uuid.uuid4().hex
                body = {key: config[key] for key in ('server_url', 'model', 'size')}
                body.update(prompt=entry['prompt'], request_id=self.request_id)
                if config.get('seed') is not None:
                    body['seed'] = (config['seed'] + ordinal) % 4294967296
                self._check()
                result = self.dataset.image_requests.generate(body, cancel_event=self.stop)
                # Queue link and sample insert commit together, including across restarts.
                self.dataset.add(dict(job['meta'], image=result['image'],
                    filename=f'synthetic-{job["id"][:8]}-{ordinal + 1:05d}.png'),
                    generation=(entry, job, result['metadata']))
                with self.lock:
                    self.request_id = None
            job.update(status='completed', error='')
        except Exception as error:
            job.update(status='cancelled' if self.stop.is_set() else 'failed', error=str(error)[:800])
            with self.lock, self.db:
                for entry in self._entries(job['id']):
                    if entry['status'] == 'generating':
                        entry.update(status='pending' if self.stop.is_set() else 'failed', error=job['error'])
                        self._entry(entry)
        finally:
            with self.lock, self.db:
                self.request_id = None
                self._save(job)

    @staticmethod
    def _new_entry(job, ordinal, prompt):
        return dict(id=uuid.uuid4().hex, job_id=job['id'], ordinal=ordinal, prompt=prompt,
                    status='pending', sample_id=None, error='', model=job['config']['model'],
                    size=job['config']['size'], requested_seed=(job['config']['seed'] + ordinal) % 4294967296
                    if job['config'].get('seed') is not None else None)
