"""Scientific composition of real retained scalar tables, no native transport."""
import copy
import struct
import unittest
from unittest.mock import patch

import retained_measurements as owner
from retained_measurements import MeasurementComparison, MeasurementTable, encode
from test_retained_measurements import fixture, source
from workbench import WorkbenchError


def partition(subject):
    document = fixture()
    document['title'] = 'Original partition ' + subject
    document['subjects'] = [item for item in document['subjects'] if item['id'] == subject]
    document['observations'] = [row for row in document['observations'] if row['subject_id'] == subject]
    return document


def selected(document, origin='a'*32):
    table = MeasurementTable(encode(document))
    return dict(origin_catalog_id=origin, packet_sha256=table.sha256), table


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.inputs = [selected(partition('a')), selected(partition('b'))]
        self.comparison = MeasurementComparison(self.inputs)

    def test_complete_maxima_and_missing_denominators_keep_original_packet(self):
        result = self.comparison.read('error')
        self.assertEqual(len(result['subjects']), 2)
        self.assertEqual(result['case_count'], 2)
        self.assertEqual(result['observation_count'], 8)
        self.assertEqual([s['maximum']['value'] for s in result['query']['summary']], [2e-15, .02])
        for row in result['query']['rows']:
            locator, original = next(item for item in self.inputs if item[0] == row['source'])
            evidence = original.inspect(row['id'])
            self.assertEqual(struct.pack('!d', row['value']), struct.pack('!d', evidence['scalar_evidence']['value']))
        missing = self.comparison.read('latency')['query']
        self.assertEqual(missing['total'], 4)
        self.assertEqual([s['states'] for s in missing['summary']], [
            dict(measured=0, failed=0, unsupported=0, unavailable=2),
            dict(measured=0, failed=1, unsupported=0, unavailable=1)])
        self.assertTrue(all(s['maximum'] is None for s in missing['summary']))

    def test_global_pages_span_packets_without_changing_maxima(self):
        full = self.comparison.read('error')['query']
        rows = []
        for offset in range(5):
            page = self.comparison.read('error', offset=offset, limit=1)['query']
            self.assertEqual(page['summary'], full['summary'])
            self.assertEqual(page['total'], 4)
            rows.extend(page['rows'])
        self.assertEqual(rows, full['rows'])
        self.assertEqual([r['subject_id'] for r in rows], ['a','a','b','b'])
        ordered = self.comparison.read('error', subject_ids=['b','a'])['query']
        self.assertEqual([s['subject_id'] for s in ordered['summary']], ['b','a'])

    def test_density_domain_device_and_unknown_filters_are_separate(self):
        density = self.comparison.read('error', filters={'cpm':16})['query']
        domain = self.comparison.read('error', filters={'grid_x':16})['query']
        self.assertEqual([s['maximum']['value'] for s in density['summary']], [1e-17,.01])
        self.assertEqual([s['maximum']['value'] for s in domain['summary']], [2e-15,.02])
        cpu = self.comparison.read('error', filters={'device':'CPU'})['query']
        self.assertEqual([s['count'] for s in cpu['summary']], [0,2])
        unknown = self.comparison.read('error', filters={'device':None})['query']
        self.assertEqual(unknown['total'], 0)
        self.assertTrue(all(s['maximum'] is None for s in unknown['summary']))

    def test_changed_original_case_evidence_or_dimension_meaning_refuses_comparison(self):
        changed = partition('b')
        context = fixture()['sources'][0]
        import base64, json
        original = json.loads(base64.b64decode(context['data_base64']))
        original['different_original_case'] = True
        changed['sources'][0] = source('context', original)
        for document in (changed, partition('b')):
            if document is not changed:
                document['dimensions'][0]['units'] = 'different units'
            with self.assertRaises(WorkbenchError) as error:
                MeasurementComparison([self.inputs[0], selected(document)])
            self.assertEqual(error.exception.code, 'incompatible')

    def test_overlapping_subjects_and_repeated_sources_are_explicit_errors(self):
        with self.assertRaises(WorkbenchError): MeasurementComparison([self.inputs[0], self.inputs[0]])
        other = partition('a'); other['title'] = 'Different packet, same subject'
        with self.assertRaises(WorkbenchError) as error:
            MeasurementComparison([self.inputs[0], selected(other)])
        self.assertEqual(error.exception.code, 'conflict')

    def test_bounds_and_invalid_selections_never_return_partial_results(self):
        for constant, maximum in [('MAX_COMPARISON_BYTES', 1), ('MAX_COMPARISON_SUBJECTS', 1), ('MAX_ROWS', 7)]:
            with patch.object(owner, constant, maximum), self.assertRaises(WorkbenchError):
                MeasurementComparison(self.inputs)
        with self.assertRaises(WorkbenchError): MeasurementComparison(self.inputs * 9)
        for arguments in ({'subject_ids':[['bad']]}, {'subject_ids':[]}, {'subject_ids':['a','a']},
                          {'subject_ids':['missing']}, {'offset':True}, {'limit':101}):
            with self.subTest(arguments=arguments), self.assertRaises(WorkbenchError):
                self.comparison.read('error', **arguments)
        with self.assertRaises(WorkbenchError): self.comparison.read(filters={})

    def test_returned_metadata_and_query_values_have_no_mutable_owner_alias(self):
        expected = self.comparison.read('error')
        result = self.comparison.read('error')
        result['query']['metric']['label'] = 'Changed'
        result['query']['summary'][0]['states']['measured'] = 99
        result['subjects'][0]['source']['origin_catalog_id'] = 'b'*32
        self.assertEqual(self.comparison.read('error'), expected)
