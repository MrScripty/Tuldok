"""Experiments-owned intent and ancestry; never an execution or evidence owner.

Trial v1 stays immutable. An optional, immutable sidecar records what an author
declared, when it was recorded, and exact derivation/comparison identities.
Overview reads inspect bounded saved Run metadata, not every artifact on disk.
"""
import copy
import math
import re

from access import authorized
from model_definitions import checked_json, natural, text
from pipeline import closed, digest, identifier
from workbench import WorkbenchError, encode, timestamp

PAGE_LIMIT = 20
ANCESTOR_LIMIT = 1000
RUN_LIMIT = 5
INTENT_LIMIT = 16 * 1024
SHA = re.compile(r'[a-f0-9]{64}')


class _BranchReplay(Exception):
    def __init__(self, result):
        self.result = result


class TrialLineage:
    def __init__(self, studies):
        self.studies = studies
        self.dataset, self.db, self.lock, self.access = (
            studies.dataset, studies.db, studies.lock, studies.access)

    def _ref(self, value):
        closed(value, ('catalog_id', 'trial_id', 'material_sha256'))
        identifier(value['trial_id'], 'Trial ID')
        if value['catalog_id'] != self.db.dataset_id:
            raise WorkbenchError('Lineage references must belong to this catalog.', 'conflict', 409)
        trial = self.studies.trial(value['trial_id'])
        if value['material_sha256'] != trial['material']['sha256']:
            raise WorkbenchError('Trial material changed or the reference is foreign.', 'stale', 409)
        return trial

    def ref(self, trial):
        return {'catalog_id': self.db.dataset_id, 'trial_id': trial['id'],
                'material_sha256': trial['material']['sha256']}

    def _intent(self, value):
        value = checked_json(value, INTENT_LIMIT)
        closed(value, ('ancestry', 'parent', 'baseline', 'cohort', 'hypothesis', 'change_summary', 'target'))
        if value['ancestry'] not in ('unknown', 'root', 'derived'):
            raise WorkbenchError('Choose unknown, root or derived ancestry.')
        if (value['ancestry'] == 'derived') != (value['parent'] is not None):
            raise WorkbenchError('Derived ancestry requires one exact parent; other ancestry has no parent.')
        for key in ('parent', 'baseline'):
            if value[key] is not None:
                self._ref(value[key])
        text(value['cohort'], 'Cohort', 120)
        text(value['hypothesis'], 'Hypothesis', 2000)
        text(value['change_summary'], 'Intended change', 2000)
        target = value['target']
        closed(target, ('metric_id', 'metric_definition_sha256', 'direction', 'threshold', 'acceptance'))
        text(target['metric_id'], 'Target metric', 80)
        if target['metric_definition_sha256'] is not None and (
                not isinstance(target['metric_definition_sha256'], str) or
                not SHA.fullmatch(target['metric_definition_sha256'])):
            raise WorkbenchError('Target metric definition requires an exact SHA256 or explicit unknown.')
        if target['direction'] not in ('minimize', 'maximize', 'target'):
            raise WorkbenchError('Target direction is unsupported.')
        if target['threshold'] is not None and (
                type(target['threshold']) not in (int, float) or not math.isfinite(target['threshold']) or
                abs(target['threshold']) > 2**53-1):
            raise WorkbenchError('Target threshold must be a finite safe number or explicit unknown.')
        text(target['acceptance'], 'Acceptance intent', 2000)
        return value

    def _version(self):
        # Both populations are append-only through their owning APIs. Live Run
        # progress does not invalidate a structural page snapshot.
        trials = self.db.execute('SELECT count(*) FROM model_trials').fetchone()[0]
        records = self.db.execute('SELECT count(*) FROM model_trial_lineage').fetchone()[0]
        return digest({'trials': trials, 'lineage_records': records})

    def _record(self, trial_id):
        row = self.db.execute('SELECT parent_trial_id,baseline_trial_id,document FROM model_trial_lineage '
                              'WHERE trial_id=%s', (trial_id,)).fetchone()
        if row is None:
            return None
        from model_definitions import retained_json
        value = retained_json(row['document'], INTENT_LIMIT + 4096)
        closed(value, ('format', 'trial', 'intent', 'actor_id', 'recorded_at', 'timing'))
        if value['format'] != 'trial_lineage_v1' or value['trial']['trial_id'] != trial_id:
            raise WorkbenchError('Stored lineage identity differs.', 'unavailable', 409)
        self._ref(value['trial'])
        intent = self._intent(value['intent'])
        if (row['parent_trial_id'] != (intent['parent'] or {}).get('trial_id') or
                row['baseline_trial_id'] != (intent['baseline'] or {}).get('trial_id') or
                value['timing'] not in ('before_admission', 'retrospective')):
            raise WorkbenchError('Stored lineage relationships differ.', 'unavailable', 409)
        return value

    def _acyclic(self, child, parent):
        seen = {child}
        for _ in range(ANCESTOR_LIMIT):
            if parent is None:
                return
            if parent in seen:
                raise WorkbenchError('Derivation would contain a cycle.', 'conflict', 409)
            seen.add(parent)
            row = self.db.execute('SELECT parent_trial_id FROM model_trial_lineage WHERE trial_id=%s',
                                  (parent,)).fetchone()
            parent = row[0] if row is not None else None
        raise WorkbenchError('Ancestry exceeds the bounded inspection depth.', 'unsupported', 409)

    def _insert(self, trial, intent):
        intent = self._intent(intent)
        child = trial['id']
        for key in ('parent', 'baseline'):
            if intent[key] is not None and intent[key]['trial_id'] == child:
                raise WorkbenchError('A trial cannot derive from or compare against itself.', 'conflict', 409)
        self._acyclic(child, (intent['parent'] or {}).get('trial_id'))
        if self._record(child) is not None:
            raise WorkbenchError('Trial lineage is already recorded and immutable.', 'conflict', 409)
        admitted = self.db.execute('SELECT 1 FROM model_attempt_reservations WHERE trial_id=%s LIMIT 1',
                                   (child,)).fetchone()
        value = {'format': 'trial_lineage_v1', 'trial': self.ref(trial), 'intent': intent,
                 'actor_id': self.access._context().actor_id, 'recorded_at': timestamp(),
                 'timing': 'retrospective' if admitted else 'before_admission'}
        self.db.execute('INSERT INTO model_trial_lineage VALUES(%s,%s,%s,%s)',
                        (child, (intent['parent'] or {}).get('trial_id'),
                         (intent['baseline'] or {}).get('trial_id'), encode(value)))
        self.access.audit('studies.lineage.record', child,
                          {'material_sha256': trial['material']['sha256'], 'intent_sha256': digest(intent)})
        return value

    @authorized('edit', 'studies.record_lineage')
    def record(self, body):
        from experiments import request_key
        body = checked_json(body, INTENT_LIMIT + 4096)
        closed(body, ('request_key', 'revision', 'trial', 'intent'))
        request_key(body['request_key'])
        actor = self.access._context().actor_id
        sha = digest(body)
        with self.lock, self.db.transaction():
            prior = self.studies._receipt(actor, 'studies.record_lineage', body['request_key'], sha)
            if prior is not None:
                return prior
            if body['revision'] != self._version():
                raise WorkbenchError('Lineage changed. Refresh before recording intent.', 'stale', 409)
            trial = self._ref(body['trial'])
            self.access.require('edit', 'studies.record_lineage', trial['id'])
            value = self._insert(trial, body['intent'])
            self.studies._save_receipt(actor, 'studies.record_lineage', body['request_key'], sha, value)
            return value

    @authorized('edit', 'studies.branch_trial')
    def branch(self, body):
        from experiments import request_key
        body = checked_json(body, INTENT_LIMIT + 4096)
        closed(body, ('request_key', 'name', 'intent'), ('new_study_name',))
        request_key(body['request_key'])
        text(body['name'], 'Branch recipe name', 120)
        actor = self.access._context().actor_id
        sha = digest(body)
        with self.lock:
            prior = self.studies._receipt(actor, 'studies.branch_trial', body['request_key'], sha)
            if prior is not None:
                return prior
            intent = self._intent(body['intent'])
            if intent['parent'] is None:
                raise WorkbenchError('Branching requires an exact parent trial.')
            parent = self._ref(intent['parent'])
        result = None

        def publish(graph, source):
            nonlocal result
            # A competing delivery may have committed while capture was read.
            prior = self.studies._receipt(actor, 'studies.branch_trial', body['request_key'], sha)
            if prior is not None:
                raise _BranchReplay(prior)
            self.access.require('edit', 'studies.branch_trial', parent['id'])
            study_id = parent['study_id']
            if 'new_study_name' in body:
                study = self.studies._study(study_id)
                policy = self.studies.policy(study['policy'])
                created = self.studies.create({'name': body['new_study_name'],
                                               'limits': study['limits'], 'policy': policy})
                study_id = created['id']
            result = {'request_key': body['request_key'], 'graph': graph,
                      'model': self.dataset.pipelines.recipe_material(parent['material'])['material']['model'],
                      'parent': intent['parent'], 'intent': intent, 'study_id': study_id, 'source': source}
            self.studies._save_receipt(actor, 'studies.branch_trial', body['request_key'], sha, result)

        try:
            self.dataset.pipelines.clone_retained(parent['material'], body['name'], _publish=publish)
        except _BranchReplay as replay:
            # The clone transaction has rolled back; only the first delivery exists.
            return replay.result
        return result

    @authorized('edit', 'studies.prepare_branch')
    def prepare(self, study_id, body, *, _graph_guard=None):
        from experiments import request_key
        closed(body, ('request_key', 'revision', 'branch_request_key', 'graph_revision', 'replicate'), ('model',))
        body = checked_json(body)
        request_key(body['request_key']); request_key(body['branch_request_key'])
        actor = self.access._context().actor_id
        sha = digest({'study_id': study_id, 'body': body})
        with self.lock:
            prior = self.studies._receipt(actor, 'studies.prepare_branch', body['request_key'], sha)
            if prior is not None:
                return prior
            row = self.db.execute('SELECT document FROM model_operation_receipts '
                                  'WHERE actor_id=%s AND operation_id=%s AND request_key=%s',
                                  (actor, 'studies.branch_trial', body['branch_request_key'])).fetchone()
            if row is None:
                raise WorkbenchError('Branch receipt is unavailable for this actor.', 'not_found', 404)
            import json
            branch = json.loads(row[0])
        original = {'request_key': body['request_key'], 'revision': body['revision'],
                    'graph_id': branch['graph']['id'], 'graph_revision': body['graph_revision'],
                    'model': body.get('model', branch['model']), 'replicate': body['replicate']}
        return self.studies.prepare_trial(study_id, original,
                    _operation_id='studies.prepare_branch', _request_sha=sha,
                    _graph_guard=_graph_guard,
                    _publish=lambda trial: self._insert(trial, branch['intent']))

    def _node(self, trial):
        record = self._record(trial['id'])
        if record is not None:
            self._acyclic(trial['id'], (record['intent']['parent'] or {}).get('trial_id'))
        material = self.dataset.pipelines._recipe_material_record(trial['material'])['material']
        study = self.studies._study(trial['study_id'])
        count, runs = self.dataset.runs._study_attempt_metadata(trial, RUN_LIMIT)
        return {'trial': trial, 'lineage': record, 'study': {'id': study['id'], 'name': study['name']},
                'recipe': {'id': material['recipe_id'], 'revision': material['recipe_revision']},
                'model': material['model'], 'attempt_count': count, 'runs': runs,
                'runs_truncated': count > len(runs)}

    @authorized('inspect', 'studies.lineage')
    def list(self, *, cursor=None, limit=PAGE_LIMIT, revision=None, cohort=None):
        if type(limit) is not int or not 1 <= limit <= PAGE_LIMIT:
            raise WorkbenchError('Lineage page limit must be between 1 and 20.')
        if cursor is not None:
            identifier(cursor, 'Lineage cursor')
            if revision is None:
                raise WorkbenchError('Later pages require the lineage revision.')
        if cohort is not None:
            text(cohort, 'Cohort', 120)
        with self.lock:
            current = self._version()
            if revision is not None and revision != current:
                raise WorkbenchError('Lineage changed between pages. Refresh the graph.', 'stale', 409)
            params = [cursor or '']
            where = 't.id>%s'
            if cohort is not None:
                where += " AND l.document::jsonb->'intent'->>'cohort'=%s"
                params.append(cohort)
            params.append(limit + 1)
            rows = self.db.execute('SELECT t.id FROM model_trials t LEFT JOIN model_trial_lineage l '
                                   'ON l.trial_id=t.id WHERE ' + where + ' ORDER BY t.id LIMIT %s', tuple(params)).fetchall()
            nodes = [self._node(self.studies.trial(row[0])) for row in rows[:limit]]
            visible = {node['trial']['id'] for node in nodes}
            stubs = {}
            for node in nodes:
                for relationship in ('parent', 'baseline'):
                    ref = ((node['lineage'] or {}).get('intent') or {}).get(relationship)
                    if ref is not None and ref['trial_id'] not in visible:
                        stubs[ref['trial_id']] = ref
            return {'revision': current, 'nodes': nodes, 'related': list(stubs.values()),
                    'next_cursor': rows[limit-1][0] if len(rows) > limit else None,
                    'limit': limit, 'cohort': cohort}

    @authorized('inspect', 'studies.lineage_trial')
    def get(self, trial_id):
        with self.lock:
            return self._node(self.studies.trial(trial_id))
