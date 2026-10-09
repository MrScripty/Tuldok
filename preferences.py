"""Explicit comparative judgments; responses and source records retain ownership."""
import json

from workbench import WorkbenchError, IDENTIFIER, MAX_TEXT, MAX_SELECTED_TEXT_BYTES, encode, text_value, timestamp

BINDING_FIELDS = {'prompt_id', 'parent_revision', 'source_revision', 'left_id', 'left_revision', 'right_id', 'right_revision'}
SELECTION_FIELDS = BINDING_FIELDS | {'id', 'revision'}


class Preferences:
    def __init__(self, workbench):
        self.w = workbench
        self.db, self.lock = workbench.db, workbench.lock
        with self.lock, self.db:
            self.db.execute('''CREATE TABLE IF NOT EXISTS workbench_preferences (
                id TEXT PRIMARY KEY, prompt_id TEXT NOT NULL, revision INTEGER NOT NULL,
                data TEXT NOT NULL)''')
            self.db.execute('CREATE INDEX IF NOT EXISTS workbench_preference_prompt ON workbench_preferences(prompt_id)')
            self.db.execute('''CREATE TABLE IF NOT EXISTS workbench_preference_history (
                id TEXT NOT NULL, revision INTEGER NOT NULL, snapshot TEXT NOT NULL,
                PRIMARY KEY(id,revision))''')

    def _get(self, identity):
        row = self.db.execute('SELECT data FROM workbench_preferences WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise WorkbenchError('Judgment not found.', 'unavailable', 404)
        return json.loads(row[0])

    def _shape(self, value, fields):
        if not isinstance(value, dict) or set(value) != fields:
            raise WorkbenchError('Supply only the exact judgment fields and revision bindings.')
        for key in ('id', 'prompt_id', 'left_id', 'right_id'):
            if not isinstance(value[key], str) or not IDENTIFIER.fullmatch(value[key]):
                raise WorkbenchError('Invalid judgment, prompt or answer ID.')
        for key in ('revision', 'parent_revision', 'source_revision', 'left_revision', 'right_revision'):
            if type(value[key]) is not int or value[key] < (0 if key == 'revision' else 1):
                raise WorkbenchError('Supply integer exact judgment/prompt/answer revisions.')
        if value['left_id'] == value['right_id']:
            raise WorkbenchError('Choose two distinct answers for the same prompt.')

    def _bindings(self, value):
        parent = self.w._get(value['prompt_id'])
        left, right = self.w._response(value['left_id']), self.w._response(value['right_id'])
        if parent['kind'] != 'text' or not parent['source_available']:
            raise WorkbenchError('Judgments require an available text prompt.')
        if any(answer['prompt_id'] != parent['id'] for answer in (left, right)):
            raise WorkbenchError('Both answers must belong to this same prompt.')
        for key, expected in (('parent_revision', parent['revision']), ('source_revision', parent['source_revision']),
                              ('left_revision', left['revision']), ('right_revision', right['revision'])):
            if value[key] != expected:
                raise WorkbenchError('Stale judgment: prompt or answer changed. Deliberately rejudge and review current revisions.', 'conflict', 409)
        from grounded_instructions import check_answer
        for answer in (left, right):
            check_answer(self.w, parent, response=answer)
        return parent, left, right

    def list(self, prompt_id):
        with self.lock:
            parent = self.w._get(prompt_id)
            result = []
            for row in self.db.execute('SELECT data FROM workbench_preferences WHERE prompt_id=? ORDER BY id', (prompt_id,)):
                judgment = json.loads(row[0]); warning = None
                try:
                    self._bindings(judgment)
                except WorkbenchError as error:
                    warning = str(error)
                result.append(dict(judgment, stale_warning=warning))
            return {'parent': parent, 'judgments': result, 'responses': self.w.responses(prompt_id)['responses']}

    def history(self, identity):
        with self.lock:
            self._get(identity)
            return {'history': [json.loads(row[0]) for row in self.db.execute(
                'SELECT snapshot FROM workbench_preference_history WHERE id=? ORDER BY revision', (identity,))]}

    def save(self, body):
        self._shape(body, SELECTION_FIELDS | {'outcome', 'rationale', 'review'})
        if body['outcome'] not in ('left', 'right', 'tie', 'abstain'):
            raise WorkbenchError('Explicitly choose left, right, tie or abstain.')
        text_value(body['rationale'], 'Judgment rationale', 4000, empty=True)
        if body['review'] not in ('draft', 'human_reviewed'):
            raise WorkbenchError('Explicitly choose draft or human review of this judgment.')
        with self.lock, self.db:
            parent, left, right = self._bindings(body)
            row = self.db.execute('SELECT data FROM workbench_preferences WHERE id=?', (body['id'],)).fetchone()
            before = json.loads(row[0]) if row else None
            if before:
                if before['deleted'] or before['revision'] != body['revision'] or before['prompt_id'] != body['prompt_id']:
                    raise WorkbenchError('Judgment changed, was deleted or belongs to another prompt. Reload before saving.', 'conflict', 409)
                if all(before[key] == body[key] for key in body):
                    return {'judgment': before, 'changed': False}
            elif body['revision'] != 0:
                raise WorkbenchError('Judgment no longer exists.', 'unavailable', 409)
            now = timestamp()
            judgment = dict(body, revision=body['revision'] + 1, deleted=False,
                            created_at=before['created_at'] if before else now, updated_at=now,
                            provenance={'method': 'human_comparative_judgment'})
            self._persist(judgment, parent, left, right)
            return {'judgment': judgment, 'changed': True}

    def _persist(self, judgment, parent, left, right):
        self.db.execute('''INSERT INTO workbench_preferences VALUES (?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,data=excluded.data''',
                        (judgment['id'], judgment['prompt_id'], judgment['revision'], encode(judgment)))
        self.db.execute('INSERT INTO workbench_preference_history VALUES (?,?,?)',
                        (judgment['id'], judgment['revision'], encode({'judgment': judgment, 'parent': parent, 'left': left, 'right': right})))

    def delete(self, body):
        self._shape(body, SELECTION_FIELDS)
        with self.lock, self.db:
            before = self._get(body['id'])
            if before['deleted'] or any(body[key] != before[key] for key in SELECTION_FIELDS):
                raise WorkbenchError('Judgment changed or was deleted. Reload before deleting.', 'conflict', 409)
            # Deletion retires even a stale judgment, but cannot silently rebind its evidence.
            snapshot = self.history(before['id'])['history'][-1]
            judgment = dict(before, deleted=True, revision=before['revision'] + 1, updated_at=timestamp())
            self._persist(judgment, snapshot['parent'], snapshot['left'], snapshot['right'])
            return {'judgment': judgment, 'changed': True}

    def competing(self, selected):
        """Only live reviewed judgments of selected exact bindings affect release proof."""
        def key(row):
            return (row['prompt_id'], row['parent_revision'], row['source_revision'],
                    tuple(sorted(((row['left_id'], row['left_revision']), (row['right_id'], row['right_revision'])))))
        keys = {key(row) for row in selected}
        result, size = [], 0
        for prompt_id in sorted({row['prompt_id'] for row in selected}):
            for (data,) in self.db.execute('SELECT data FROM workbench_preferences WHERE prompt_id=?', (prompt_id,)):
                row = json.loads(data)
                if row['deleted'] or row['review'] != 'human_reviewed' or key(row) not in keys:
                    continue
                size += len(data.encode('utf-8'))
                if len(result) >= 5000 or size > MAX_SELECTED_TEXT_BYTES:
                    raise WorkbenchError('Competing reviewed judgment evidence exceeds the 5,000-unit/40 MiB release bound.')
                result.append(row)
        return sorted(result, key=lambda row: row['id'])

    def selection(self, items):
        if not isinstance(items, list) or not 1 <= len(items) <= 5000:
            raise WorkbenchError('Select 1–5,000 explicit judgment revisions.')
        judgments, parents, answers, excluded, seen, directions = [], {}, {}, [], set(), {}
        size = 0
        for item in items:
            self._shape(item, SELECTION_FIELDS)
            if item['id'] in seen:
                raise WorkbenchError('Repeated judgment selection.')
            seen.add(item['id'])
            judgment = self._get(item['id'])
            if judgment['deleted'] or any(item[key] != judgment[key] for key in SELECTION_FIELDS):
                raise WorkbenchError('Selected judgment changed or was deleted. Explicitly reselect.', 'conflict', 409)
            parent, left, right = self._bindings(judgment)
            if judgment['review'] != 'human_reviewed':
                raise WorkbenchError('Every selected judgment needs independent explicit human review.')
            if parent['id'] not in parents:
                parents[parent['id']] = parent; size += len(parent['text'].encode('utf-8'))
            for answer in (left, right):
                text_value(answer['completion'], 'Completion', MAX_TEXT)
                if answer['id'] not in answers:
                    answers[answer['id']] = answer; size += len(answer['completion'].encode('utf-8'))
            if size > MAX_SELECTED_TEXT_BYTES:
                raise WorkbenchError('Selected preference text exceeds 40 MiB.')
            judgments.append(judgment)
            if judgment['outcome'] in ('tie', 'abstain'):
                excluded.append({'id': judgment['id'], 'revision': judgment['revision'], 'reason': judgment['outcome']})
                continue
            chosen = left if judgment['outcome'] == 'left' else right
            key = (parent['id'], parent['revision'], parent['source_revision'], *sorted(((left['id'], left['revision']), (right['id'], right['revision']))))
            if key in directions and directions[key] != chosen['id']:
                raise WorkbenchError('Conflicting selected judgments choose opposite answers for the same exact pair.', 'conflict', 409)
            directions[key] = chosen['id']
        # A fixed selection cannot hide current dissent on its exact evidence.
        for other in self.competing(judgments):
            if other['outcome'] in ('tie', 'abstain'):
                continue
            key = (other['prompt_id'], other['parent_revision'], other['source_revision'],
                   *sorted(((other['left_id'], other['left_revision']), (other['right_id'], other['right_revision']))))
            chosen_id = other[other['outcome'] + '_id']
            if key in directions and directions[key] != chosen_id:
                raise WorkbenchError('Conflicting current reviewed judgments choose opposite answers for this exact pair.', 'conflict', 409)
        if len(excluded) == len(judgments):
            raise WorkbenchError('All selected judgments are tie/abstain; no directional preference rows to export.')
        return (sorted(judgments, key=lambda row: row['id']), sorted(parents.values(), key=lambda row: row['id']),
                sorted(answers.values(), key=lambda row: row['id']), sorted(excluded, key=lambda row: row['id']))
