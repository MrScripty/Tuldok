"""Finite retained scalar tables, exact source bindings and explicit missingness.

This owner validates data representation and performs fixed selections/reductions.
Producers own metric definitions, comparison scope and scientific interpretation.
It reads no paths, runs no producer and grants no evidence/disclosure authority.
"""
import base64
import binascii
import copy
from decimal import Decimal
import hashlib
import json
import math
import re
import struct

from workbench import WorkbenchError


FORMAT = 'retained_measurements_v1'
MAX_BYTES = 32 * 1024 * 1024
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_TOTAL = 16 * 1024 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
MAX_ROWS = 100000
MAX_COMPARISON_SOURCES = 16
MAX_COMPARISON_SUBJECTS = 256
MAX_COMPARISON_BYTES = 128 * 1024 * 1024
STATES = ('measured', 'failed', 'unsupported', 'unavailable')
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
SHA = re.compile(r'^[a-f0-9]{64}$')


def fail(message, code='invalid', status=400):
    raise WorkbenchError('Retained measurements: ' + message, code, status)


def exact(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        fail('Object fields differ from schema 1.')


def text(value, maximum=240):
    if (type(value) is not str or not value.strip() or len(value) > maximum
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value)):
        fail('Bounded nonempty display text required.')
    try:
        value.encode('utf-8')
    except UnicodeError:
        fail('Text must contain valid Unicode scalars.')
    return value


def identifier(value):
    if type(value) is not str or not ID.fullmatch(value):
        fail('Invalid declared identity.')
    return value


def number(value):
    return (type(value) is int and abs(value) <= 2**53-1
            or type(value) is float and math.isfinite(value))


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                fail('Duplicate JSON key.')
            result[key] = value
        return result
    def floating(value):
        result = float(value)
        if not math.isfinite(result) or result == 0 and Decimal(value) != 0:
            fail('JSON number exceeds finite binary64 range.')
        return result
    def constant(_value):
        fail('Nonfinite JSON constants are unsupported.')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                           parse_float=floating, parse_constant=constant)
        pending = [(value, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 24:
                fail('JSON nesting exceeds the supported bound.', 'too_large', 413)
            if type(item) is dict:
                pending.extend((v, depth+1) for v in item.values())
                for key in item:
                    key.encode('utf-8')
            elif type(item) is list:
                pending.extend((v, depth+1) for v in item)
            elif type(item) is str:
                item.encode('utf-8')
        return value
    except (ValueError, UnicodeError, RecursionError):
        fail('Unique-key finite UTF-8 JSON required.')


def collection(values, maximum):
    if type(values) is not list or not values:
        fail('Nonempty declared collection required.')
    if len(values) > maximum:
        fail('Declared collection exceeds its supported bound.', 'too_large', 413)
    result = {}
    for value in values:
        if type(value) is not dict:
            fail('Declared entries must be objects.')
        identity = identifier(value.get('id'))
        if identity in result:
            fail('Duplicate declared identity.')
        result[identity] = value
    return result


def cell(kind, value):
    if value is None:
        return True
    if kind == 'string':
        return type(value) is str and len(value) <= 256
    if kind == 'boolean':
        return type(value) is bool
    if kind == 'integer':
        return type(value) is int and abs(value) <= 2**53-1
    return kind == 'number' and number(value)


class MeasurementTable:
    """Own an immutable input snapshot; returned projections are independent."""
    def __init__(self, raw):
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
            fail('A bounded complete byte snapshot is required.', 'too_large', 413)
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.bytes = len(raw)
        doc = decode(raw)
        exact(doc, ('format', 'schema_version', 'title', 'scope', 'dimensions', 'subjects',
                    'cases', 'metrics', 'observations', 'sources'))
        if doc['format'] != FORMAT or type(doc['schema_version']) is not int or doc['schema_version'] != 1:
            fail('Unsupported measurement schema.', 'unsupported', 409)
        text(doc['title'])
        self._doc = doc
        self._sources = collection(doc['sources'], 256)
        self._json = {}
        total = 0
        for identity, source in self._sources.items():
            exact(source, ('id', 'label', 'kind', 'bytes', 'sha256', 'data_base64'))
            text(source['label'])
            if source['kind'] not in ('json', 'opaque'):
                fail('Unsupported retained source kind.', 'unsupported', 409)
            if type(source['bytes']) is not int or not 0 < source['bytes'] <= MAX_SOURCE_BYTES:
                fail('Source byte declaration exceeds its bound.', 'too_large', 413)
            total += source['bytes']
            if total > MAX_SOURCE_TOTAL:
                fail('Source collection exceeds its decoded byte bound.', 'too_large', 413)
            if type(source['sha256']) is not str or not SHA.fullmatch(source['sha256']):
                fail('Source requires an exact SHA256.')
            value = source['data_base64']
            if type(value) is not str or len(value) != 4*((source['bytes']+2)//3):
                fail('Source encoding differs from its byte declaration.')
            try:
                payload = base64.b64decode(value, validate=True)
            except (ValueError, binascii.Error):
                fail('Invalid source base64.')
            if (len(payload) != source['bytes'] or hashlib.sha256(payload).hexdigest() != source['sha256']
                    or base64.b64encode(payload).decode('ascii') != value):
                fail('Retained source bytes differ from their declaration.')
            if source['kind'] == 'json':
                self._json[identity] = decode(payload)
        scope = doc['scope']
        exact(scope, ('id', 'label', 'population', 'definition'))
        identifier(scope['id']);text(scope['label'])
        if scope['population'] not in ('training', 'consumed', 'independent', 'reserved', 'unknown'):
            fail('Unsupported declared population.', 'unsupported', 409)
        self._definition(scope, ('id', 'label', 'population'))
        if type(doc['dimensions']) is not list or len(doc['dimensions']) > 32:
            fail('Invalid dimension collection.')
        self._dimensions = collection(doc['dimensions'], 32) if doc['dimensions'] else {}
        for dimension in self._dimensions.values():
            exact(dimension, ('id', 'label', 'type', 'units', 'scope'))
            text(dimension['label'])
            if dimension['scope'] not in ('subject', 'case', 'observation'):
                fail('Unsupported dimension owner.', 'unsupported', 409)
            if dimension['type'] not in ('string', 'number', 'integer', 'boolean'):
                fail('Unsupported dimension type.', 'unsupported', 409)
            if dimension['units'] is not None:
                text(dimension['units'], 120)
        self._subjects = collection(doc['subjects'], MAX_ROWS)
        self._cases = collection(doc['cases'], 4096)
        self._metrics = collection(doc['metrics'], 32)
        expected = len(self._subjects)*len(self._cases)*len(self._metrics)
        if expected > MAX_ROWS:
            fail('Complete subject/case/metric matrix exceeds its row bound.', 'too_large', 413)
        for subject in self._subjects.values():
            exact(subject, ('id', 'label', 'dimensions', 'reference'));text(subject['label']);self._reference(subject['reference'])
            self._dimension_values('subject',subject['dimensions'])
        for case in self._cases.values():
            exact(case, ('id', 'dimensions', 'reference'))
            self._dimension_values('case',case['dimensions'])
            self._reference(case['reference'])
        for metric in self._metrics.values():
            exact(metric, ('id', 'label', 'units', 'definition'));text(metric['label']);text(metric['units'], 120)
            self._definition(metric, ('id', 'label', 'units'))
        observations = doc['observations']
        if type(observations) is not list or len(observations) != expected:
            fail('Every subject/case/metric needs one explicit result, including missing or failed results.')
        self._observations = collection(observations, MAX_ROWS)
        pairs = set()
        for observation in observations:
            exact(observation, ('id', 'subject_id', 'case_id', 'metric_id', 'state', 'value', 'reason', 'dimensions', 'reference'))
            self._dimension_values('observation',observation['dimensions'])
            identity = observation['subject_id'], observation['case_id'], observation['metric_id']
            for value in identity:
                identifier(value)
            if (identity in pairs or identity[0] not in self._subjects or identity[1] not in self._cases
                    or identity[2] not in self._metrics):
                fail('Duplicate or unresolved measurement identity.')
            pairs.add(identity)
            if observation['state'] not in STATES:
                fail('Unsupported observation state.', 'unsupported', 409)
            source_value = self._reference(observation['reference'])
            if observation['state'] == 'measured':
                value = observation['value']
                if (not number(value) or not number(source_value) or observation['reason'] is not None
                        or struct.pack('!d', float(value)) != struct.pack('!d', float(source_value))):
                    fail('Measured scalar differs from its exact retained source value.')
            else:
                if observation['value'] is not None:
                    fail('Unmeasured results require an explicit null value.')
                text(observation['reason'], 1000)

    def _dimension_values(self,scope,values):
        columns={k:d for k,d in self._dimensions.items() if d['scope']==scope}
        if type(values) is not dict or set(values)!=set(columns):
            fail('Dimension values differ from their declared owner and columns.')
        if any(not cell(columns[k]['type'],v) for k,v in values.items()):
            fail('Dimension value differs from its declared type.')

    def _row_dimensions(self,row):
        return {**self._subjects[row['subject_id']]['dimensions'],
                **self._cases[row['case_id']]['dimensions'],**row['dimensions']}

    def _reference(self, reference, *, hashed=False):
        exact(reference, ('source_id', 'pointer', 'sha256') if hashed else ('source_id', 'pointer'))
        source = self._sources.get(identifier(reference['source_id']))
        if source is None:
            fail('Source reference is unresolved.')
        pointer = reference['pointer']
        if pointer is None and not hashed:
            return None
        if (type(pointer) is not str or len(pointer) > 512 or pointer and not pointer.startswith('/')
                or re.search(r'~(?:[^01]|$)', pointer) or source['kind'] != 'json'):
            fail('A bounded existing JSON pointer is required.')
        value = self._json[source['id']]
        try:
            for part in pointer[1:].split('/') if pointer else ():
                part = part.replace('~1', '/').replace('~0', '~')
                if type(value) is dict:
                    value = value[part]
                elif type(value) is list and re.fullmatch(r'0|[1-9][0-9]*', part):
                    value = value[int(part)]
                else:
                    fail('Source pointer does not identify a retained value.')
        except (KeyError, IndexError):
            fail('Source pointer does not identify a retained value.')
        if hashed and reference['sha256'] != digest(value):
            fail('Declared definition digest differs from its retained source.')
        return value

    def _definition(self, descriptor, fields):
        value = self._reference(descriptor['definition'], hashed=True)
        if type(value) is not dict or len(encode(value)) > 16384 or any(value.get(k) != descriptor[k] for k in fields):
            fail('Definition metadata differs from its exact retained document.')
        return value

    def metadata(self):
        return copy.deepcopy({'format': FORMAT, 'packet_sha256': self.sha256, 'title': self._doc['title'],
            'scope': self._doc['scope'], 'scope_definition':self._definition(self._doc['scope'],('id','label','population')),
            'dimensions': self._doc['dimensions'], 'metrics': self._doc['metrics'],
            'subject_count':len(self._subjects),'case_count': len(self._cases),
            'observation_count': len(self._observations),'source_count':len(self._sources)})

    def subjects(self, *, offset=0, limit=40):
        if type(offset) is not int or not 0<=offset<=2**53-1 or type(limit) is not int or not 1<=limit<=40:
            fail('Invalid subject page bounds.')
        return copy.deepcopy({'items':list(self._subjects.values())[offset:offset+limit],
                              'offset':offset,'limit':limit,'total':len(self._subjects)})

    def query(self, metric_id, *, subject_ids=None, filters=None, offset=0, limit=50):
        identifier(metric_id)
        if metric_id not in self._metrics:
            fail('Metric is unavailable.', 'not_found', 404)
        selected = list(self._subjects) if subject_ids is None else subject_ids
        if (type(selected) is not list or not selected or len(selected)>MAX_ROWS or any(type(v) is not str for v in selected)
                or len(set(selected)) != len(selected) or any(v not in self._subjects for v in selected)):
            fail('Choose existing unique subjects.')
        filters = {} if filters is None else filters
        if (type(filters) is not dict or any(k not in self._dimensions or not cell(self._dimensions[k]['type'],v)
                                          for k,v in filters.items())):
            fail('Filters must use declared dimensions and typed scalar values.')
        if type(offset) is not int or not 0<=offset<=2**53-1 or type(limit) is not int or not 1<=limit<=100:
            fail('Page bounds must be explicit finite integers.')
        rows = [v for v in self._doc['observations'] if v['metric_id']==metric_id
                and v['subject_id'] in selected
                and all(self._row_dimensions(v)[k]==wanted for k,wanted in filters.items())]
        summaries = []
        for identity in selected:
            own = [v for v in rows if v['subject_id']==identity]
            counts = {state:sum(v['state']==state for v in own) for state in STATES}
            measured = [v for v in own if v['state']=='measured']
            maximum = max(measured, key=lambda v:v['value']) if measured else None
            summaries.append({'subject_id':identity,'count':len(own),'states':counts,
                'maximum':None if maximum is None else {k:maximum[k] for k in ('id','case_id','value')}})
        result = {'format':'retained_measurement_query_v1','packet_sha256':self.sha256,
            'scope':copy.deepcopy(self._doc['scope']),'metric':copy.deepcopy(self._metrics[metric_id]),
            'scope_definition':copy.deepcopy(self._definition(self._doc['scope'],('id','label','population'))),
            'definition':copy.deepcopy(self._definition(self._metrics[metric_id],('id','label','units'))),
            'filters':copy.deepcopy(filters),'subject_ids':list(selected),'summary':summaries,
            'rows':[dict(copy.deepcopy(v),dimensions=copy.deepcopy(self._row_dimensions(v)))
                    for v in rows[offset:offset+limit]],
            'total':len(rows),'offset':offset,'limit':limit,'sampling':'none'}
        if len(encode(result)) > MAX_RESPONSE_BYTES:
            fail('Selected response exceeds its bound; choose a smaller page.', 'too_large', 413)
        return result

    def inspect(self, observation_id):
        identifier(observation_id)
        observation = self._observations.get(observation_id)
        if observation is None:
            fail('Observation is unavailable.', 'not_found', 404)
        reference = observation['reference'];source = self._sources[reference['source_id']]
        return copy.deepcopy({'packet_sha256':self.sha256,'observation':observation,
            'case':self._cases[observation['case_id']],'subject':self._subjects[observation['subject_id']],
            'metric':self._metrics[observation['metric_id']],'scope':self._doc['scope'],
            'scope_definition':self._definition(self._doc['scope'],('id','label','population')),
            'case_evidence':self._inspection_reference(self._cases[observation['case_id']]['reference']),
            'scalar_evidence':self._inspection_reference(reference),
            'source':{k:v for k,v in source.items() if k!='data_base64'}})

    def _inspection_reference(self,reference):
        value=self._reference(reference)
        state='opaque' if reference['pointer'] is None else 'included'
        if state=='included' and len(encode(value))>16384:
            state='exceeds_inspection_bound';value=None
        return {'reference':copy.deepcopy(reference),'source_sha256':self._sources[reference['source_id']]['sha256'],
                'state':state,'value':value}


class MeasurementComparison:
    """One bounded scientific comparison over immutable, source-bound tables.

    The native custody owner supplies validated locator/table pairs. Compatibility
    depends on original definitions and actual case evidence, not display names.
    Returned rows keep their packet locator; no observations or counts are pooled
    across subjects. Pagination affects rows only, never the maximum denominator.
    """
    def __init__(self, tables):
        if type(tables) is not list or not 1 <= len(tables) <= MAX_COMPARISON_SOURCES:
            fail('Choose 1 through 16 comparison sources.', 'too_large', 413)
        self._tables = []
        self._subjects = {}
        seen = set()
        basis = None
        observations = raw_bytes = 0
        for locator, table in tables:
            exact(locator, ('origin_catalog_id', 'packet_sha256'))
            if (type(locator['origin_catalog_id']) is not str
                    or not re.fullmatch('[a-f0-9]{32}', locator['origin_catalog_id'])
                    or not isinstance(table, MeasurementTable) or locator['packet_sha256'] != table.sha256):
                fail('Comparison source differs from its validated packet.')
            key = (locator['origin_catalog_id'], locator['packet_sha256'])
            if key in seen:
                fail('Comparison repeats a source.')
            seen.add(key)
            raw_bytes += table.bytes
            if raw_bytes > MAX_COMPARISON_BYTES:
                fail('Comparison exceeds 128 MiB of original packets.', 'too_large', 413)
            metadata = table.metadata()
            cases = []
            for case in table._cases.values():
                reference = case['reference']
                evidence = table._reference(reference)
                cases.append(dict(id=case['id'], dimensions=case['dimensions'], evidence=evidence,
                    opaque_source_sha256=table._sources[reference['source_id']]['sha256']
                    if reference['pointer'] is None else None))
            current = dict(scope=metadata['scope_definition'], dimensions=metadata['dimensions'],
                metrics=[table._definition(metric, ('id','label','units')) for metric in table._metrics.values()],
                cases=cases)
            # Canonical source bytes distinguish Boolean/numeric values too;
            # ordinary Python equality is not the scientific identity relation.
            identity = digest(current)
            if basis is None:
                basis = identity
                self._header = dict(format='retained_measurement_comparison_v1',
                    scope=metadata['scope'], scope_definition=metadata['scope_definition'],
                    dimensions=metadata['dimensions'], metrics=metadata['metrics'],
                    definition_source=copy.deepcopy(locator), case_population_sha256=digest(cases),
                    case_count=metadata['case_count'])
            elif identity != basis:
                fail('Comparison sources have different scope, metric, dimension or original case definitions.', 'incompatible', 409)
            for subject in table._subjects.values():
                if subject['id'] in self._subjects:
                    fail('Comparison sources overlap a subject identity.', 'conflict', 409)
                self._subjects[subject['id']] = dict(copy.deepcopy(subject), source=copy.deepcopy(locator))
            observations += metadata['observation_count']
            if len(self._subjects) > MAX_COMPARISON_SUBJECTS or observations > MAX_ROWS:
                fail('Comparison exceeds 256 subjects or 100,000 observations.', 'too_large', 413)
            self._tables.append((copy.deepcopy(locator), table))
        self._header.update(subjects=list(self._subjects.values()), observation_count=observations)

    def read(self, metric_id=None, *, subject_ids=None, filters=None, offset=0, limit=50):
        result = copy.deepcopy(self._header)
        result['query'] = None
        if metric_id is None:
            if subject_ids is not None or filters is not None or offset != 0 or limit != 50:
                fail('A comparison selection requires an explicit metric.')
            return self._bounded(result)
        selected = list(self._subjects) if subject_ids is None else subject_ids
        if (type(selected) is not list or not selected
                or any(type(value) is not str or value not in self._subjects for value in selected)
                or len(set(selected)) != len(selected)):
            fail('Choose existing unique comparison subjects.')
        if type(offset) is not int or not 0 <= offset <= 2**53-1 or type(limit) is not int or not 1 <= limit <= 100:
            fail('Comparison page bounds must be finite integers.')
        summaries = {}
        rows = []
        total = 0
        template = None
        for locator, table in self._tables:
            own = [identity for identity in selected if identity in table._subjects]
            if not own:
                continue
            page = table.query(metric_id, subject_ids=own, filters=filters, offset=0, limit=1)
            if template is None:
                template = page
            for summary in page['summary']:
                summaries[summary['subject_id']] = dict(summary, source=copy.deepcopy(locator))
            start = max(0, offset-total)
            if total+page['total'] > offset and len(rows) < limit:
                current = table.query(metric_id, subject_ids=own, filters=filters,
                    offset=start, limit=limit-len(rows))
                rows.extend(dict(row, source=copy.deepcopy(locator)) for row in current['rows'])
            total += page['total']
        metric = next(item for item in self._header['metrics'] if item['id'] == metric_id)
        result['query'] = dict(metric=copy.deepcopy(metric), definition=template['definition'],
            filters=template['filters'], subject_ids=list(selected),
            summary=[summaries[identity] for identity in selected], rows=rows,
            total=total, offset=offset, limit=limit, sampling='none')
        return self._bounded(result)

    @staticmethod
    def _bounded(value):
        if len(encode(value)) > MAX_RESPONSE_BYTES:
            fail('Comparison response exceeds its bound; choose fewer sources or a smaller page.', 'too_large', 413)
        return value
