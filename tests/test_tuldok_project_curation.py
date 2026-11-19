"""Curation by embeddings (docs/plans/training-and-curation/spec-t5.md).

T5a: the contract, the principal components against the test's own
arithmetic on a planted structure, and the searches (neighbours, duplicates,
outliers, leakage, thin cells) against a brute force the test computes, on
fixtures with planted near-duplicates, one far record and one leaked
validation record. Every fixture is written by the test with the standard
library. No database for these.

T5b (classes further down): the default embedder, the settings, the steps
embed and select and freeze's records, against tests/fake_pumas_typed.py.
"""
import base64
import json
import math
import os
from pathlib import Path
import random
import statistics
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tuldok_project import embeddings, inside  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402

DIMENSIONS = 24


def unit(vector):
    norm = math.sqrt(sum(item * item for item in vector))
    return [item / norm for item in vector]


def cosine(a, b):
    return sum(x * y for x, y in zip(unit(a), unit(b)))


def floats(text):
    raw = base64.b64decode(text)
    return list(struct.unpack(f'<{len(raw) // 4}f', raw))


def write_set(root, name, ids, rows, *, records=None, **index):
    """embeddings/<name>.npy and .json under root (and records.jsonl when records is given)."""
    directory = Path(root) / embeddings.DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    dimensions = len(rows[0]) if rows else 1
    embeddings.write_npy(directory / f'{name}.npy', len(rows), dimensions, [item for row in rows for item in row])
    value = {'format': embeddings.FORMAT, 'records': list(ids), 'dimensions': dimensions, 'metric': 'cosine',
             'model': {'name': 'stand-in', 'via': 'test'}, 'prefix': None,
             'source': {'dataset': None, 'run': None}}
    value.update(index)
    (directory / f'{name}.json').write_text(json.dumps(value), encoding='utf-8')
    if records is not None:
        with open(Path(root) / 'records.jsonl', 'w', encoding='utf-8') as handle:
            for record in records:
                handle.write(json.dumps(record) + '\n')
    return value


def fixture(seed=5):
    """(ids, rows, records, planted): six clusters of records with splits, two pairs of near-duplicates in train,
    one validation record that is a near-copy of a training one, and one record far from everything."""
    generator = random.Random(seed)
    centres = [[generator.gauss(0, 1) for _ in range(DIMENSIONS)] for _ in range(6)]
    ids, rows, records = [], [], []
    for i in range(180):
        centre = centres[i % 6]
        rows.append([value + generator.gauss(0, 0.35) for value in centre])
        ids.append(f'r{i:03d}')
        split = 'validation' if i % 10 == 3 else 'test' if i % 10 == 7 else 'train'
        records.append({'id': ids[-1], 'kind': 'text', 'text': f'record {i}', 'split': split,
                        'meta': {'cluster': f'c{i % 6}', 'size': i}, 'annotations': {'quality': {
                            'state': 'accepted', 'value': 'good' if i % 2 else 'bad'}}})

    def near_copy(row):
        return [value + generator.gauss(0, 0.003) for value in row]

    planted = {'duplicates': [('r010', 'd001'), ('r020', 'd002')], 'leaked': ('v001', 'r040'), 'far': 'far01'}
    for copy_of, name, split in (('r010', 'd001', 'train'), ('r020', 'd002', 'train'), ('r040', 'v001', 'validation')):
        rows.append(near_copy(rows[ids.index(copy_of)]))
        ids.append(name)
        records.append({'id': name, 'kind': 'text', 'text': 'copy', 'split': split})
    far = [generator.gauss(0, 1) for _ in range(DIMENSIONS)]
    rows.append(far)
    ids.append('far01')
    records.append({'id': 'far01', 'kind': 'image', 'path': 'far.png', 'split': 'train'})
    return ids, rows, records, planted


class Product(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.addCleanup(embeddings.forget)
        embeddings.forget()

    def product(self, root=None):
        return inside.Product('run-test', root or self.root)


class Contract(Product):
    """Section 1: a set read; each rule broken once."""

    def test_a_set_is_read_and_listed(self):
        ids, rows, records, _ = fixture()
        write_set(self.root, 'texts', ids, rows, records=records, prefix='task: clustering | query: ',
                  notes=['One note.'])
        listed = embeddings.sets(self.product())
        self.assertEqual([(item['name'], item['problem']) for item in listed], [('texts', None)])
        shown = embeddings.described(listed[0]['index'])
        self.assertEqual((shown['rows'], shown['dimensions'], shown['prefix'], shown['projection'], shown['notes']),
                         (len(ids), DIMENSIONS, 'task: clustering | query: ', None, ['One note.']))
        (self.root / 'nothing-here').mkdir()
        self.assertEqual(embeddings.sets(self.product(self.root / 'nothing-here')), [])

    def refusal(self, **change):
        ids, rows, _, _ = fixture()
        write_set(self.root, 'broken', ids, rows)
        index_path = self.root / 'embeddings' / 'broken.json'
        value = json.loads(index_path.read_text())
        for key, item in change.items():
            if item is KeyError:
                value.pop(key)
            else:
                value[key] = item
        index_path.write_text(json.dumps(value))
        listed = embeddings.sets(self.product())
        self.assertEqual(listed[0]['index'], None)
        with self.assertRaises(ProjectError) as raised:
            embeddings.embedding_map(self.product(), self.product(), 'broken')
        self.assertEqual(str(raised.exception), listed[0]['problem'])
        return raised.exception

    def test_each_rule_of_the_index(self):
        cases = {'format': ('tuldok_embeddings_v0', 'Its format must be'),
                 'records': (['a', 'a'], "The record id 'a' is listed more than once."),
                 'dimensions': (0, 'dimensions must be a whole number'),
                 'metric': ('dot', 'metric must be "cosine"'),
                 'model': ({'via': 'x'}, 'model must be an object with a name'),
                 'prefix': (7, 'prefix must be a string'),
                 'source': ({'dataset': 'photos', 'run': None}, 'source.dataset must be a reference'),
                 'projection': ({'file': 'x.txt', 'method': 'umap'}, 'projection must be null or an object'),
                 'notes': (['x' * 1001], 'notes must be a list')}
        for key, (value, words) in cases.items():
            with self.subTest(key):
                self.assertIn(words, str(self.refusal(**{key: value})))
        self.assertIn('records must be a list', str(self.refusal(records=KeyError)))
        self.assertIn('is not 1 to 200 characters', str(self.refusal(records=['a/b'])))

    def test_the_vectors_and_the_projection(self):
        ids, rows, _, _ = fixture()
        write_set(self.root, 'short', ids[:-1], rows)
        with self.assertRaises(ProjectError) as raised:
            embeddings.analysis(self.product(), 'short')
        self.assertIn('has the shape (184, 24); the index says (183, 24)', str(raised.exception))
        bad = [list(row) for row in rows]
        bad[3][5] = float('nan')
        write_set(self.root, 'nan', ids, bad)
        with self.assertRaises(ProjectError) as raised:
            embeddings.analysis(self.product(), 'nan')
        self.assertEqual(str(raised.exception), 'Row 3 of the vectors holds a value that is not finite.')
        zero = [list(row) for row in rows]
        zero[7] = [0.0] * DIMENSIONS
        write_set(self.root, 'zero', ids, zero)
        with self.assertRaises(ProjectError) as raised:
            embeddings.analysis(self.product(), 'zero')
        self.assertIn('Row 7 of the vectors is all zeros', str(raised.exception))
        write_set(self.root, 'mapped', ids, rows, projection={'file': 'mapped.map.npy', 'method': 'umap'})
        embeddings.write_npy(self.root / 'embeddings' / 'mapped.map.npy', len(ids), 3, [0.0] * len(ids) * 3)
        with self.assertRaises(ProjectError) as raised:
            embeddings.embedding_map(self.product(), self.product(), 'mapped')
        self.assertIn('mapped.map.npy has the shape (184, 3); the index says (184, 2)', str(raised.exception))
        with mock.patch.object(embeddings, 'VALUES_LIMIT', 1000):
            with self.assertRaises(ProjectError) as raised:
                embeddings.analysis(self.product(), 'nan')
        self.assertEqual(raised.exception.code, 'too-large')
        with self.assertRaises(ProjectError) as raised:
            embeddings.analysis(self.product(), 'absent')
        self.assertEqual(raised.exception.code, 'not-found')
        with self.assertRaises(ProjectError) as raised:
            embeddings.analysis(self.product(), '../records')
        self.assertEqual(raised.exception.code, 'invalid')


class Components(Product):
    """The map's components against the test's own arithmetic on a planted structure."""

    def planted(self, count=400, dimensions=12):
        generator = random.Random(11)
        u = unit([generator.gauss(0, 1) for _ in range(dimensions)])
        v = [generator.gauss(0, 1) for _ in range(dimensions)]
        dot = sum(a * b for a, b in zip(u, v))
        v = unit([b - dot * a for a, b in zip(u, v)])
        offset = [3.0] + [0.0] * (dimensions - 1)
        sample = [[offset[d] + 3.0 * a * u[d] + 1.5 * b * v[d] + generator.gauss(0, 0.05) for d in range(dimensions)]
                  for a, b in ((generator.gauss(0, 1), generator.gauss(0, 1)) for _ in range(count))]
        return sample, u, v

    def own_covariance(self, sample):
        count, size = len(sample), len(sample[0])
        mean = [sum(row[d] for row in sample) / count for d in range(size)]
        return [[sum((row[i] - mean[i]) * (row[j] - mean[j]) for row in sample) / count for j in range(size)]
                for i in range(size)], mean

    def check(self, sample, u, v):
        mean, components, variances, total, turns = embeddings.principal_components(sample, 4)
        covariance, own_mean = self.own_covariance(sample)
        self.assertTrue(all(abs(a - b) < 1e-9 for a, b in zip(mean, own_mean)))
        self.assertAlmostEqual(total, sum(covariance[i][i] for i in range(len(covariance))), places=9)
        for c, variance in zip(components, variances):
            moved = [sum(row[j] * c[j] for j in range(len(c))) for row in covariance]
            self.assertLess(max(abs(m - variance * x) for m, x in zip(moved, c)), 1e-6 * variances[0])
            self.assertAlmostEqual(sum(x * x for x in c), 1.0, places=9)
            self.assertGreater(max(c, key=abs), 0)
        for a in range(4):
            for b in range(a + 1, 4):
                self.assertAlmostEqual(sum(x * y for x, y in zip(components[a], components[b])), 0.0, places=9)
        self.assertEqual(variances, sorted(variances, reverse=True))
        # The sample's own directions differ from the planted ones by its sampling alone.
        self.assertGreater(abs(sum(x * y for x, y in zip(components[0], u))), 0.995)
        self.assertGreater(abs(sum(x * y for x, y in zip(components[1], v))), 0.995)
        own = [sum(x * y for x, y in zip(c, [sum(cov[j] * c[j] for j in range(len(c))) for cov in covariance]))
               for c in components]
        for mine, theirs in zip(own, variances):
            self.assertAlmostEqual(mine, theirs, delta=1e-8 * variances[0])
        self.assertAlmostEqual(variances[0] / total, own[0] / total, places=9)
        self.assertGreater(variances[0] / total, 0.7)
        self.assertLess(turns, embeddings.POWER_TURNS)

    def test_planted_directions_and_variances(self):
        self.check(*self.planted())

    def test_the_covariance_applied_without_forming_it(self):
        with mock.patch.object(embeddings, 'COVARIANCE_DIMENSIONS', 4):
            self.check(*self.planted())

    def test_the_map_and_a_scripts_projection(self):
        sample, u, v = self.planted(count=300)
        ids = [f'p{i}' for i in range(len(sample))]
        write_set(self.root, 'planted', ids, sample, records=[{'id': i, 'kind': 'text', 'text': i} for i in ids])
        drawn = embeddings.embedding_map(self.product(), self.product(), 'planted')
        self.assertEqual((drawn['method'], drawn['rows'], drawn['sample'], drawn['missing']), ('pca', 300, 300, 0))
        # The map's x is each unit row's coordinate on the first component of the unit rows: the test's own.
        rows = [unit(row) for row in sample]
        mean, components, variances, total, _ = embeddings.principal_components(rows, 8)
        own_x = [sum((r[d] - mean[d]) * components[0][d] for d in range(len(r))) for r in rows]
        self.assertLess(max(abs(a - b) for a, b in zip(floats(drawn['x_f32']), own_x)), 1e-5)
        self.assertAlmostEqual(drawn['explained'][0], variances[0] / total, places=6)   # rows kept as float32
        mapped = [[float(i), float(-i)] for i in range(300)]
        write_set(self.root, 'mapped', ids, sample, projection={'file': 'mapped.map.npy', 'method': 'umap'})
        embeddings.write_npy(self.root / 'embeddings' / 'mapped.map.npy', 300, 2,
                             [value for pair in mapped for value in pair])
        drawn = embeddings.embedding_map(self.product(), self.product(), 'mapped')
        self.assertEqual((drawn['method'], drawn['explained'], drawn['bounds']), ('umap', None, [0.0, 299.0, -299.0, 0.0]))
        self.assertEqual(floats(drawn['y_f32'])[:3], [0.0, -1.0, -2.0])


class Searched(Product):
    """Neighbours, duplicates, outliers, leakage, thin cells and colours against the test's brute force."""

    def setUp(self):
        super().setUp()
        self.ids, self.rows, self.records, self.planted = fixture()
        write_set(self.root, 'texts', self.ids, self.rows, records=self.records)
        self.units = [unit(row) for row in self.rows]

    def brute(self, threshold):
        found = {}
        for a in range(len(self.ids)):
            for b in range(a + 1, len(self.ids)):
                value = sum(x * y for x, y in zip(self.units[a], self.units[b]))
                if value >= threshold:
                    found[tuple(sorted((self.ids[a], self.ids[b])))] = value
        return found

    def test_neighbours_are_the_brute_forces(self):
        got = embeddings.embedding_neighbours(self.product(), self.product(), 'texts', record='r010', limit=5)
        i = self.ids.index('r010')
        own = sorted(((sum(x * y for x, y in zip(self.units[i], self.units[j])), self.ids[j])
                      for j in range(len(self.ids)) if j != i), reverse=True)[:5]
        self.assertEqual([item['id'] for item in got['neighbours']], [name for _, name in own])
        self.assertEqual(got['neighbours'][0]['id'], 'd001')
        self.assertAlmostEqual(got['neighbours'][0]['cosine'], own[0][0], places=6)
        self.assertEqual((got['neighbours'][0]['split'], got['neighbours'][0]['kind']), ('train', 'text'))
        with self.assertRaises(ProjectError) as raised:
            embeddings.embedding_neighbours(self.product(), self.product(), 'texts', record='nobody')
        self.assertEqual(raised.exception.code, 'not-found')

    def test_duplicates_are_the_brute_forces(self):
        for threshold in (0.999, 0.98, 0.9):
            with self.subTest(threshold):
                embeddings.forget()
                got = embeddings.embedding_duplicates(self.product(), self.product(), 'texts', threshold=threshold,
                                                      limit=10_000)
                own = self.brute(threshold)
                self.assertEqual({tuple(sorted((pair['a'], pair['b']))) for pair in got['pairs']}, set(own))
                self.assertTrue(got['complete'])
                self.assertEqual((got['examined'], got['rows'], got['total']), (184, 184, len(own)))
                for pair in got['pairs']:
                    self.assertAlmostEqual(pair['cosine'], own[tuple(sorted((pair['a'], pair['b'])))], places=6)
        got = embeddings.embedding_duplicates(self.product(), self.product(), 'texts', threshold=0.999)
        self.assertEqual({tuple(sorted((pair['a'], pair['b']))) for pair in got['pairs']},
                         {('d001', 'r010'), ('d002', 'r020'), ('r040', 'v001')})
        self.assertEqual(got['groups'], 6)
        self.assertEqual([pair['cosine'] for pair in got['pairs']], sorted([pair['cosine'] for pair in got['pairs']],
                                                                          reverse=True))

    def test_a_lowered_budget_lists_exactly_the_pairs_of_the_rows_examined(self):
        with mock.patch.object(embeddings, 'EXACT_VALUES_BUDGET', DIMENSIONS * 300):
            got = embeddings.embedding_duplicates(self.product(), self.product(), 'texts', threshold=0.9, limit=10_000)
        self.assertFalse(got['complete'])
        self.assertTrue(0 < got['examined'] < 184)
        made = embeddings.analysis(self.product(), 'texts')
        examined = {self.ids[i] for i in made.shuffled()[:got['examined']]}
        own = {pair for pair in self.brute(0.9) if set(pair) & examined}
        self.assertEqual({tuple(sorted((pair['a'], pair['b']))) for pair in got['pairs']}, own)

    def test_outliers_are_the_brute_forces(self):
        got = embeddings.embedding_outliers(self.product(), self.product(), 'texts', k=3, limit=184)
        own = []
        for i in range(len(self.ids)):
            distances = sorted(1 - sum(x * y for x, y in zip(self.units[i], self.units[j]))
                               for j in range(len(self.ids)) if j != i)
            own.append((distances[2], self.ids[i]))
        own.sort(reverse=True)
        self.assertTrue(got['complete'])
        self.assertEqual(got['outliers'][0]['id'], 'far01')
        self.assertEqual([item['id'] for item in got['outliers'][:10]], [name for _, name in own[:10]])
        by = {item['id']: item['distance'] for item in got['outliers']}
        self.assertLess(max(abs(by[name] - distance) for distance, name in own), 1e-6)
        self.assertAlmostEqual(got['median'], statistics.median(distance for distance, _ in own), places=6)

    def test_leakage_finds_the_leaked_validation_record(self):
        got = embeddings.embedding_leakage(self.product(), self.product(), 'texts', threshold=0.99)
        self.assertEqual(got['splits'], {'test': 18, 'train': 147, 'validation': 19})
        self.assertEqual([(pair['record'], pair['split'], pair['near']) for pair in got['pairs']],
                         [('v001', 'validation', 'r040')])
        self.assertEqual((got['leaked'], got['complete'], got['examined']), (1, True, 37))
        loose = embeddings.embedding_leakage(self.product(), self.product(), 'texts', threshold=0.9, limit=10_000)
        split = {record['id']: record['split'] for record in self.records}
        own = {(a, b) if split[a] != 'train' else (b, a) for a, b in self.brute(0.9)
               if (split[a] == 'train') != (split[b] == 'train')}
        self.assertEqual({(pair['record'], pair['near']) for pair in loose['pairs']}, own)
        none = embeddings.embedding_leakage(self.product(), self.product(), 'texts', train='nothing')
        self.assertEqual((none['pairs'], none['total']), ([], 0))

    def test_the_map_its_colours_and_thin_cells(self):
        drawn = embeddings.embedding_map(self.product(), self.product(), 'texts', colour='split', cells=8, thin=0.5)
        self.assertEqual(drawn['colours'], ['split', 'kind', 'annotation:quality', 'field:cluster', 'field:size'])
        colour = drawn['colour']
        self.assertEqual(colour['type'], 'category')
        self.assertEqual([(item['name'], item['count']) for item in colour['categories']],
                         [('train', 147), ('validation', 19), ('test', 18)])
        raw = base64.b64decode(colour['codes_u16'])
        codes = struct.unpack(f'<{len(raw) // 2}H', raw)
        names = [item['name'] for item in colour['categories']]
        self.assertEqual([names[code] for code in codes], [record['split'] for record in self.records])
        # The grid and thin cells against the test's own counting of the drawn points.
        xs, ys = floats(drawn['x_f32']), floats(drawn['y_f32'])
        x0, x1, y0, y1 = drawn['bounds']
        counts = [[0] * 8 for _ in range(8)]
        for x, y in zip(xs, ys):
            counts[min(7, int((y - y0) / (y1 - y0) * 8))][min(7, int((x - x0) / (x1 - x0) * 8))] += 1
        self.assertEqual(drawn['grid'], {'cells': 8, 'counts': counts})
        filled = [count for line in counts for count in line if count]
        most = 0.5 * statistics.median(filled)
        own = sorted((count, line, column) for line, row in enumerate(counts) for column, count in enumerate(row)
                     if count and count <= most)
        self.assertEqual([(cell['count'], *cell['cell']) for cell in drawn['thin']], own)
        self.assertTrue(own)
        numbers = embeddings.embedding_map(self.product(), self.product(), 'texts', colour='field:size')['colour']
        self.assertEqual(numbers['type'], 'number')
        self.assertEqual(floats(numbers['values_f32'])[:3], [0.0, 1.0, 2.0])
        self.assertTrue(math.isnan(floats(numbers['values_f32'])[-1]))
        tasks = embeddings.embedding_map(self.product(), self.product(), 'texts', colour='annotation:quality')
        self.assertEqual([item['name'] for item in tasks['colour']['categories']], ['bad', 'good'])
        with self.assertRaises(ProjectError) as raised:
            embeddings.embedding_map(self.product(), self.product(), 'texts', colour='size')
        self.assertEqual(raised.exception.code, 'invalid')

    def test_records_of_another_product_and_missing_ones(self):
        other = self.root / 'records-elsewhere'
        other.mkdir()
        with open(other / 'records.jsonl', 'w', encoding='utf-8') as handle:
            for record in self.records[:100]:
                handle.write(json.dumps(record) + '\n')
        drawn = embeddings.embedding_map(self.product(), inside.Product('run-records', other), 'texts')
        self.assertEqual(drawn['missing'], 84)


if __name__ == '__main__':
    unittest.main()
