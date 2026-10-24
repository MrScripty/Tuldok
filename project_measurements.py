"""Native custody and current access for immutable retained scalar packets.

The scalar owner interprets the packet. ProjectArtifacts owns bytes and
ProjectSession owns publication/receipts. Retained source paths are facts only;
reads after Open need no current source registration or producer execution.
"""
import copy
from datetime import datetime

from project_artifacts import validate_declaration
from project_material import decode_records as material_records
from projects import ID, NAME, SHA, relative_path
from retained_measurements import (MeasurementTable, MeasurementComparison, MAX_BYTES, MAX_RESPONSE_BYTES,
    MAX_COMPARISON_SOURCES, MAX_COMPARISON_BYTES, encode, text)
from workbench import WorkbenchError, timestamp


FAMILY = 'measurement_source'
FORMAT = 'project_measurement_source_v1'
FIELDS = {'format', 'origin_catalog_id', 'id', 'title', 'blob', 'source', 'actor_id', 'imported_at'}


def _closed(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise WorkbenchError('Invalid native measurement source fields.')


def _identity(value, pattern):
    if type(value) is not str or not pattern.fullmatch(value):
        raise WorkbenchError('Invalid native measurement source identity.')
    return value


def declaration(blob):
    return validate_declaration(dict(format='project_artifact_v1', **blob))


def _document(value):
    _closed(value, FIELDS)
    if value['format'] != FORMAT:
        raise WorkbenchError('Unsupported native measurement source format.', 'unsupported', 409)
    for key in ('origin_catalog_id', 'actor_id'):
        _identity(value[key], ID)
    _identity(value['id'], SHA)
    text(value['title'])
    _closed(value['blob'], ('sha256', 'bytes'))
    blob = declaration(value['blob'])
    if not 0 < blob['bytes'] <= MAX_BYTES or blob['sha256'] != value['id']:
        raise WorkbenchError('Measurement packet identity or byte bound differs.')
    source = value['source']
    _closed(source, ('origin_catalog_id', 'project_id', 'manifest_sha256', 'reference_id', 'path', 'measured_sha256'))
    for key in ('origin_catalog_id', 'project_id'):
        _identity(source[key], ID)
    for key in ('manifest_sha256', 'measured_sha256'):
        _identity(source[key], SHA)
    _identity(source['reference_id'], NAME)
    relative_path(source['path'])
    if source['measured_sha256'] != blob['sha256']:
        raise WorkbenchError('Measurement source capture hash differs from its packet.')
    try:
        if type(value['imported_at']) is not str or len(value['imported_at']) > 80:
            raise ValueError()
        if datetime.fromisoformat(value['imported_at']).utcoffset() is None:
            raise ValueError()
    except ValueError:
        raise WorkbenchError('Measurement import requires an attributed timestamp.') from None
    return value


def decode_records(records, *, artifacts=None):
    """Validate candidate closure, including exact available packet bytes.

    Missing payloads remain discoverable as missing. They never yield numerical
    results. Present payloads must pass custody and scalar-source validation.
    """
    declarations = {item['id']: item['document'] for item in records if item['family'] == 'project_artifact'}
    snapshots = material_records(records)
    result = {}
    for item in records:
        if item['family'] != FAMILY:
            continue
        doc = _document(item['document'])
        identity = doc['origin_catalog_id'] + '.' + doc['id']
        if item['id'] != identity or identity in result:
            raise WorkbenchError('Duplicate or inconsistent native measurement identity.')
        if declarations.get(doc['blob']['sha256']) != declaration(doc['blob']):
            raise WorkbenchError('Measurement artifact declaration is missing or inconsistent.')
        source = doc['source']
        snapshot = snapshots.get(('project_snapshot', source['origin_catalog_id'] + '.' + source['manifest_sha256']))
        if snapshot is None or snapshot['value']['id'] != source['project_id']:
            raise WorkbenchError('Measurement source snapshot is missing or inconsistent.')
        reference = next((r for r in snapshot['value']['manifest']['data'] if r['id'] == source['reference_id']), None)
        if (reference is None or reference['path'] != source['path']
                or reference.get('sha256', source['measured_sha256']) != source['measured_sha256']):
            raise WorkbenchError('Measurement capture differs from its retained source reference.')
        if artifacts is not None and artifacts.inspect(declaration(doc['blob']))['state'] != 'missing':
            table = MeasurementTable(artifacts.read_blob(doc['blob'], maximum_bytes=MAX_BYTES))
            if table.metadata()['title'] != doc['title']:
                raise WorkbenchError('Measurement title differs from the exact retained packet.')
        result[identity] = copy.deepcopy(doc)
    return result


def validate_operation_result(operation, result, records=None):
    if operation != 'measurements.import':
        return False
    _document(result)
    if records is not None:
        identity = result['origin_catalog_id'] + '.' + result['id']
        if decode_records(records).get(identity) != result:
            raise WorkbenchError('Measurement receipt has no exact retained source.')
    return True


class ProjectMeasurements:
    def __init__(self, session):
        self.session, self.artifacts = session, session.artifacts
        self.access, self.db = session.access, session.db

    def _documents(self):
        return decode_records(self.session.snapshot['records'])

    def import_packet(self, raw, source, expected_checkpoint, key):
        """Called only after SourceAdapter's explicit current rooted capture."""
        with self.access.lock, self.session.lock, self.db.lock:
            actor = self.access.require('edit', 'measurements.import')
            self.session.check()
            table = MeasurementTable(raw)
            blob = dict(sha256=table.sha256, bytes=len(raw))
            origin = self.session.snapshot['project_id']
            request = dict(blob=blob, source=copy.deepcopy(source))

            def invoke():
                prior = self._documents().get(origin + '.' + table.sha256)
                if prior is not None:
                    if prior['source'] != source:
                        raise WorkbenchError('This packet already has different retained capture facts.', 'conflict', 409)
                    return prior
                self.artifacts.publish_bytes(raw, declaration(blob), maximum_bytes=MAX_BYTES)
                return dict(format=FORMAT, origin_catalog_id=origin, id=table.sha256,
                    title=table.metadata()['title'], blob=blob, source=copy.deepcopy(source),
                    actor_id=actor.actor_id, imported_at=timestamp())

            def capture(result, before):
                return dict(records=[dict(family='project_artifact', id=table.sha256, document=declaration(blob)),
                    dict(family=FAMILY, id=origin + '.' + table.sha256, document=result)], result=result)

            return self.session.mutate('measurements.import', table.sha256, request, expected_checkpoint, key, invoke, capture)

    def sources(self, *, offset=0, limit=40):
        if type(offset) is not int or not 0 <= offset <= 2**53-1 or type(limit) is not int or not 1 <= limit <= 40:
            raise WorkbenchError('Invalid measurement source page.')
        with self.access.lock, self.session.lock, self.db.lock:
            self.access.require('inspect', 'measurements.sources')
            self.session.check()
            docs = sorted(self._documents().values(), key=lambda d: (d['origin_catalog_id'], d['id']))
            items = [dict(doc, availability=self.artifacts.inspect(declaration(doc['blob'])))
                     for doc in docs[offset:offset+limit]]
            self.session.check()
            self.access.require('inspect', 'measurements.sources')
            return self._bounded(dict(items=items, total=len(docs), offset=offset, limit=limit))

    @staticmethod
    def _bounded(value):
        if len(encode(value)) > MAX_RESPONSE_BYTES:
            raise WorkbenchError('Measurement response exceeds its bound; select a smaller page.', 'too_large', 413)
        return value

    def _read(self, origin_catalog_id, packet_sha256, action, select):
        _identity(origin_catalog_id, ID)
        _identity(packet_sha256, SHA)
        target = origin_catalog_id + '.' + packet_sha256
        with self.access.lock, self.session.lock, self.db.lock:
            self.access.require('inspect', action, target)
            self.session.check()
            doc = self._documents().get(target)
            if doc is None:
                raise WorkbenchError('Measurement source is unavailable.', 'not_found', 404)
            raw = self.artifacts.read_blob(doc['blob'], maximum_bytes=MAX_BYTES)
            table = MeasurementTable(raw)
            if table.metadata()['title'] != doc['title']:
                raise WorkbenchError('Measurement title differs from the exact retained packet.')
            value = self._bounded(dict(source=doc, value=select(table)))
            self.session.check()
            self.access.require('inspect', action, target)
            return value

    def metadata(self, origin_catalog_id, packet_sha256):
        return self._read(origin_catalog_id, packet_sha256, 'measurements.metadata', lambda table: table.metadata())

    def subjects(self, origin_catalog_id, packet_sha256, *, offset=0, limit=40):
        return self._read(origin_catalog_id, packet_sha256, 'measurements.subjects',
                          lambda table: table.subjects(offset=offset, limit=limit))

    def query(self, origin_catalog_id, packet_sha256, metric_id, **selection):
        return self._read(origin_catalog_id, packet_sha256, 'measurements.query',
                          lambda table: table.query(metric_id, **selection))

    def inspect(self, origin_catalog_id, packet_sha256, observation_id):
        return self._read(origin_catalog_id, packet_sha256, 'measurements.inspect',
                          lambda table: table.inspect(observation_id))

    def compare(self, sources, metric_id=None, **selection):
        """Read one checkpoint's bounded group with every original source intact."""
        if type(sources) is not list or not 1 <= len(sources) <= MAX_COMPARISON_SOURCES:
            raise WorkbenchError('Choose 1 through 16 native measurement sources.', 'too_large', 413)
        targets = []
        for source in sources:
            _closed(source, ('origin_catalog_id','packet_sha256'))
            _identity(source['origin_catalog_id'], ID)
            _identity(source['packet_sha256'], SHA)
            targets.append(source['origin_catalog_id'] + '.' + source['packet_sha256'])
        if len(set(targets)) != len(targets):
            raise WorkbenchError('Native comparison repeats a measurement source.')
        with self.access.lock, self.session.lock, self.db.lock:
            for target in targets:
                self.access.require('inspect', 'measurements.compare', target)
            self.session.check()
            documents = self._documents()
            if any(target not in documents for target in targets):
                raise WorkbenchError('A comparison source is unavailable.', 'not_found', 404)
            chosen = [documents[target] for target in targets]
            if sum(doc['blob']['bytes'] for doc in chosen) > MAX_COMPARISON_BYTES:
                raise WorkbenchError('Native comparison exceeds 128 MiB of original packets.', 'too_large', 413)
            tables = []
            for locator, doc in zip(sources, chosen):
                raw = self.artifacts.read_blob(doc['blob'], maximum_bytes=MAX_BYTES)
                table = MeasurementTable(raw)
                if table.metadata()['title'] != doc['title']:
                    raise WorkbenchError('Comparison title differs from its original packet.')
                tables.append((locator, table))
            value = MeasurementComparison(tables).read(metric_id, **selection)
            result = self._bounded(dict(sources=chosen, value=value))
            self.session.check()
            for target in targets:
                self.access.require('inspect', 'measurements.compare', target)
            return result
