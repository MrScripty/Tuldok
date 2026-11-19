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

import hashlib  # noqa: E402
import subprocess  # noqa: E402
import uuid  # noqa: E402

import agent_api  # noqa: E402
from tuldok_project import builds, check, embeddings, inside, local, operations, plan, pumas, store  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402
import test_tuldok_project_pumas as fixtures  # noqa: E402

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
        self.assertIn('is not 1 to 600 characters', str(self.refusal(records=['a\tb'])))

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


# ======================================================================= T5b

def embedder(model, model_id, *, text=True, image=False, profile=None, dimensions=768, input_count=16):
    capabilities = []
    if text:
        capabilities.append(fixtures._capability('text_embedding', ['text', 'text_batch'], ['embeddings_float32'],
                                                 ['text'], ['vector'],
                                                 [{'option': 'dimensions', 'minimum': 1.0, 'maximum': float(dimensions)},
                                                  {'option': 'input_count', 'minimum': 1.0,
                                                   'maximum': float(input_count)}]))
    if image:
        capabilities.append(fixtures._capability('multimodal_embedding', ['png_base64', 'jpeg_base64', 'content_batch'],
                                                 ['embeddings_float32'], ['text', 'image'], ['vector'],
                                                 [{'option': 'dimensions', 'minimum': 1.0, 'maximum': float(dimensions)},
                                                  {'option': 'image_count', 'minimum': 1.0, 'maximum': 4.0}]))
    entry = fixtures._model(model, profile or f'{model}-gpu', capabilities, ['text'] + (['image'] if image else []),
                            ['vector'])
    entry['model_id'] = model_id
    return entry


def embedding_listing(*extra, gemma=True):
    value = fixtures.listing()
    if gemma:
        value['models'].append(embedder('embeddinggemma-2', 'unsloth/embeddinggemma-2-GGUF', image=True))
    value['models'].append(embedder('nomic-embed', 'nomic-ai/nomic-embed-text-v1.5-GGUF'))
    value['models'] += list(extra)
    return value


def decoded(raw):
    import pumas_operations
    return pumas_operations.decode_served_models(json.dumps(raw).encode())


def vector_of(content, size):
    digest = hashlib.sha256(content.encode('utf-8') if isinstance(content, str) else content).digest()
    return [(digest[i % 32] / 255.0 - 0.5) + 0.01 * i for i in range(size)]


def embed_respond(body):
    """The fake's answer to an embeddings request: a vector made from each item's text or image."""
    size = (body.get('options') or {}).get('dimensions', 12)
    if body['input']['kind'] == 'text_batch':
        items = body['input']['texts']
    else:
        items = [base64.b64decode(item['parts'][0]['data_base64']) for item in body['input']['items']]
    return {'kind': 'embeddings', 'vectors': [vector_of(item, size) for item in items]}


class Embedder(unittest.TestCase):
    """Section 2: EmbeddingGemma 2 by default, never another model silently."""

    def test_embeddinggemma_2_is_chosen_by_alias_or_model_id_the_released_gguf_first(self):
        listing = decoded(embedding_listing())
        entry, named_by = pumas.choose_embedder(listing)
        self.assertEqual((entry['model'], entry['model_id'], named_by),
                         ('embeddinggemma-2', 'unsloth/embeddinggemma-2-GGUF', 'default'))
        # By its model id alone, and the released GGUF before another build of it.
        other = embedder('gemma-embed-q8', 'someone/EmbeddingGemma-2-Q8')
        listing = decoded(embedding_listing(other, embedder('local-gemma', 'unsloth/EmbeddingGemma-2-GGUF'),
                                            gemma=False))
        self.assertEqual(pumas.choose_embedder(listing)[0]['model'], 'local-gemma')
        listing = decoded(embedding_listing(other, gemma=False))
        self.assertEqual(pumas.choose_embedder(listing)[0]['model'], 'gemma-embed-q8')
        # A named model comes first.
        self.assertEqual(pumas.choose_embedder(decoded(embedding_listing()), 'nomic-embed')[0]['model'],
                         'nomic-embed')

    def test_refused_when_not_served_naming_the_served_embedders(self):
        listing = decoded(embedding_listing(gemma=False))
        with self.assertRaises(pumas.PumasError) as raised:
            pumas.choose_embedder(listing)
        self.assertEqual(raised.exception.code, 'not-found')
        message = str(raised.exception)
        self.assertIn('does not serve EmbeddingGemma 2', message)
        self.assertIn('nomic-embed (nomic-ai/nomic-embed-text-v1.5-GGUF, nomic-embed-gpu)', message)
        self.assertIn('Tuldok does not choose another', message)
        # A served EmbeddingGemma 2 whose capability is unavailable is not chosen either.
        down = embedder('embeddinggemma-2', 'unsloth/embeddinggemma-2-GGUF')
        down['capabilities'][0]['availability'] = {'state': 'unavailable', 'reason': 'not_loaded'}
        with self.assertRaises(pumas.PumasError):
            pumas.choose_embedder(decoded(embedding_listing(down, gemma=False)))
        with self.assertRaises(pumas.PumasError) as raised:
            pumas.choose_embedder(decoded(embedding_listing()), 'writer')
        self.assertIn('has no embedding capability', str(raised.exception))
        shown = pumas.embedder_shown(listing, {'model': None, 'profile': None, 'prefix': None})
        self.assertEqual((shown['chosen'], shown['named_by'], shown['prefix'], len(shown['embedders'])),
                         (None, 'default', 'task: clustering | query: ', 1))
        self.assertIn('does not serve EmbeddingGemma 2', shown['problem'])

    def test_routes_batches_and_the_result(self):
        listing = decoded(embedding_listing())
        entry = pumas.choose_embedder(listing)[0]
        routes = pumas.embedding_routes(entry)
        self.assertEqual({kind: route[:2] for kind, route in routes.items()},
                         {'text': ('text_embedding', 'text_batch'), 'image': ('multimodal_embedding', 'content_batch')})
        self.assertEqual((pumas.batch_size('text', routes['text'][2], 32), pumas.batch_size('image', routes['image'][2], 32)),
                         (16, 4))
        with self.assertRaises(pumas.PumasError) as raised:
            pumas.check_dimensions(routes, 1024)
        self.assertIn('dimensions 1024 is outside the bound 1 to 768', str(raised.exception))
        import pumas_operations
        value = pumas_operations.result(json.dumps({'contract_version': 1, 'request_id': 'r', 'result': {
            'kind': 'embeddings', 'vectors': [[0.5, 1.0], [1, 2]]}}).encode(), 'r')
        self.assertEqual(value['vectors'], [[0.5, 1.0], [1, 2]])
        for vectors in ([[1.0], [1.0, 2.0]], [], [[]]):
            with self.assertRaises(pumas_operations.OperationError):
                pumas_operations.result(json.dumps({'contract_version': 1, 'request_id': 'r', 'result': {
                    'kind': 'embeddings', 'vectors': vectors}}).encode(), 'r')


class Settings(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.file = Path(directory.name) / 'settings.json'
        patcher = mock.patch.dict(os.environ, {local.SETTINGS_VARIABLE: str(self.file)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_machines_embedder_beside_the_endpoint(self):
        local.set_pumas_endpoint('http://127.0.0.1:8765')
        local.set_embedder('nomic-embed', None, 'task: search result | query: ')
        self.assertEqual(local.embedder_settings(), {'model': 'nomic-embed', 'profile': None,
                                                     'prefix': 'task: search result | query: '})
        local.set_pumas_endpoint(None)
        self.assertEqual(local.embedder_settings()['model'], 'nomic-embed')
        local.set_embedder(None, None, None)
        self.assertEqual(json.loads(self.file.read_text()), {'format': local.SETTINGS_FORMAT})
        self.file.write_text(json.dumps({'format': local.SETTINGS_FORMAT, 'embedding_model': ''}))
        with self.assertRaises(local.SettingsError):
            local.embedder_settings()


def _embed(settings=None, source='datasets/notes'):
    return {'format': 'tuldok_definition_v1', 'kind': 'dataset', 'title': 'Embedded',
            'run': {'step': 'embed', 'inputs': {'records': source}, 'settings': dict(settings or {})}}


def _select(records, source='datasets/notes'):
    return {'format': 'tuldok_definition_v1', 'kind': 'dataset', 'title': 'Picked',
            'run': {'step': 'select', 'inputs': {'records': source}, 'settings': {'records': list(records)}}}


CURATION = {
    'datasets/notes': fixtures._import({'source': 'data/notes'}),
    'datasets/notes-embedded': _embed({'dimensions': 8, 'batch': 2}),
    'datasets/notes-named': _embed({'model': 'nomic-embed', 'name': 'by-nomic', 'prefix': ''}),
    'datasets/picked': _select(['c.txt', 'a.txt', 'photo.png']),
    'datasets/picked-wrong': _select(['a.txt', 'nobody.txt']),
    'annotations/quality': fixtures._task('datasets/notes', 'class', ['good', 'bad'], title='Quality'),
    'datasets/notes-frozen': {'format': 'tuldok_definition_v1', 'kind': 'dataset', 'title': 'Frozen',
                              'run': {'step': 'freeze', 'inputs': {'records': 'datasets/notes'},
                                      'annotations': ['annotations/quality'],
                                      'settings': {'seed': 7, 'shares': {'train': 1},
                                                   'records': ['a.txt', 'b.txt', 'd.txt']}}},
}
NOTES = {'a.txt': 'A note about apples.', 'b.txt': 'A note about boats.', 'c.txt': 'A note about cats.',
         'd.txt': 'A note about dogs.', 'e.txt': 'A note about eels.'}


def write_curation_project(root, project_id):
    folder, code = root / 'project', root / 'code'
    for directory in ('datasets', 'annotations'):
        (folder / directory).mkdir(parents=True)
    (folder / 'tuldok.json').write_text(json.dumps({'format': 'tuldok_project_v1', 'id': project_id,
                                                    'name': 'Curation test project', 'code_root': '../code'},
                                                   indent=2) + '\n', encoding='utf-8')
    for reference, document in CURATION.items():
        (folder / f'{reference}.json').write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
    lines = ''.join(json.dumps({'record': name, 'sha256': None, 'state': 'accepted' if name != 'b.txt' else 'rejected',
                                'value': 'good' if name != 'b.txt' else None, 'by': 'owner',
                                'at': '2026-11-19T10:00:00Z'}, separators=(',', ':')) + '\n'
                    for name in ('a.txt', 'b.txt', 'c.txt', 'd.txt'))
    (folder / 'annotations' / 'quality.jsonl').write_text(lines, encoding='utf-8')
    notes = code / 'data' / 'notes'
    notes.mkdir(parents=True)
    for name, text in NOTES.items():
        (notes / name).write_text(text, encoding='utf-8')
    (notes / 'photo.png').write_bytes(fixtures.png())
    (notes / 'shape.xyz').write_text('0 0 0\n1 1 1\n', encoding='utf-8')


class Checked(unittest.TestCase):
    """check on the settings of embed, select and freeze's records."""

    def problems(self, document):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_curation_project(root, uuid.uuid4().hex)
            (root / 'project' / 'datasets' / 'probe.json').write_text(json.dumps(document), encoding='utf-8')
            report = check.check_folder(root / 'project')
        return {(problem.pointer, problem.severity) for problem in report.problems
                if problem.path == 'datasets/probe.json'}

    def test_the_curation_project_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_curation_project(root, uuid.uuid4().hex)
            report = check.check_folder(root / 'project')
        self.assertEqual([problem for problem in report.problems if problem.severity == 'error'], [])

    def test_settings_refused(self):
        self.assertEqual(self.problems(_embed()), set())
        self.assertEqual(self.problems(_embed({'dimensions': 0, 'batch': 999, 'name': 'Bad Name', 'prefix': 3,
                                               'profile': 'p', 'colour': 1})),
                         {('/run/settings/dimensions', 'error'), ('/run/settings/batch', 'error'),
                          ('/run/settings/name', 'error'), ('/run/settings/prefix', 'error'),
                          ('/run/settings/profile', 'error'), ('/run/settings/colour', 'error')})
        document = _embed()
        document['run']['inputs'] = {'prompts': 'datasets/notes'}
        self.assertIn(('/run/inputs', 'error'), self.problems(document))
        self.assertEqual(self.problems(_select(['a.txt'])), set())
        self.assertEqual(self.problems(_select([])), {('/run/settings/records', 'error')})
        self.assertEqual(self.problems(_select(['a.txt', 'a.txt'])), {('/run/settings/records', 'error')})
        self.assertEqual(self.problems(_select(['a\nb'])), {('/run/settings/records/0', 'error')})
        frozen = json.loads(json.dumps(CURATION['datasets/notes-frozen']))
        frozen['run']['settings']['records'] = 'a.txt'
        self.assertEqual(self.problems(frozen), {('/run/settings/records', 'error')})


@unittest.skipUnless(fixtures.DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Built(fixtures.Endpoint):
    """embed, select and freeze's records built for real by builds.execute against the fake."""

    def setUp(self):
        super().setUp()
        self.fake['served_models'] = embedding_listing()
        self.fake['respond'] = embed_respond
        self.root = self.temporary / 'repository'
        self.root.mkdir()
        self.project_id = uuid.uuid4().hex
        write_curation_project(self.root, self.project_id)
        self.folder = self.root / 'project'
        self.git('init', '-q')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'The project.')
        self.addCleanup(store.drop_project, self.project_id)
        from tuldok_project.service import Service
        self.service = Service(self.folder)
        self.addCleanup(self.service.close)
        self.addCleanup(embeddings.forget)

    git = fixtures.Project.git
    call = fixtures.Project.call
    refused = fixtures.Project.refused
    build = fixtures.Project.build
    product = fixtures.Project.product

    def set_endpoint(self):
        return self.call('set_endpoint', {'address': self.base})

    def stdout(self, item):
        return (Path(item['directory']) / 'stdout.log').read_text(encoding='utf-8')

    def test_text_and_images_embedded_by_embeddinggemma_2_in_batches(self):
        self.set_endpoint()
        done = self.build('datasets/notes-embedded')
        notes = self.product('datasets/notes')
        made = self.product('datasets/notes-embedded')
        files = sorted(str(path.relative_to(made['directory'])) for path in Path(made['directory']).rglob('*')
                       if path.is_file())
        self.assertEqual(files, ['embeddings/notes.json', 'embeddings/notes.npy'])
        index = json.loads((Path(made['directory']) / 'embeddings' / 'notes.json').read_text())
        self.assertEqual(index['records'], ['a.txt', 'b.txt', 'c.txt', 'd.txt', 'e.txt', 'photo.png'])
        self.assertEqual((index['dimensions'], index['prefix'], index['source']),
                         (8, 'task: clustering | query: ', {'dataset': 'datasets/notes', 'run': notes['run_id']}))
        self.assertEqual(index['model'], {'name': 'embeddinggemma-2', 'model_id': 'unsloth/embeddinggemma-2-GGUF',
                                          'profile': 'embeddinggemma-2-gpu',
                                          'capability': 'multimodal_embedding, text_embedding', 'dimensions_asked': 8,
                                          'named_by': 'default', 'via': 'pumas'})
        self.assertEqual(index['notes'], ['1 pointcloud records were not embedded: Pumas 0.8.0 embeds texts and images.'])
        posts = self.posts()
        self.assertEqual([(body['capability'], body['input']['kind'], len(body['input'].get('texts') or
                                                                           body['input'].get('items')))
                          for body in posts],
                         [('text_embedding', 'text_batch', 2), ('text_embedding', 'text_batch', 2),
                          ('text_embedding', 'text_batch', 1), ('multimodal_embedding', 'content_batch', 1)])
        self.assertEqual(posts[0]['input']['texts'], ['task: clustering | query: A note about apples.',
                                                      'task: clustering | query: A note about boats.'])
        self.assertEqual((posts[0]['output'], posts[0]['options'], posts[0]['model'], posts[0]['profile']),
                         ('embeddings_float32', {'kind': 'embeddings', 'dimensions': 8}, 'embeddinggemma-2',
                          'embeddinggemma-2-gpu'))
        self.assertEqual(posts[3]['input']['items'][0]['parts'][0]['encoding'], 'png')
        # The rows are the vectors the endpoint answered, in the index's order.
        product = inside.Product(made['run_id'], made['directory'])
        analysis = embeddings.analysis(product, 'notes')
        expected = unit(vector_of('task: clustering | query: A note about cats.', 8))
        self.assertLess(max(abs(a - b) for a, b in zip(analysis.row(2), expected)), 1e-6)
        self.assertIn('"stage":"embed","completed":6,"total":6', self.stdout(done['steps'][-1]))
        self.assertEqual(fixtures.Project.run_row(self, done['steps'][-1]['run_id'])['endpoint'],
                         {'address': self.base, 'version': '0.8.0'})
        # Found from the dataset it describes, and read through the operations.
        listed = self.call('embeddings', {'dataset': 'notes'}, actor=fixtures.EDITOR)
        self.assertEqual((listed['dataset'], listed['run']), ('datasets/notes', notes['run_id']))
        [found] = listed['sets']
        self.assertEqual({key: found[key] for key in ('run', 'holder', 'name', 'rows', 'dimensions', 'records_run',
                                                      'current', 'problem')},
                         {'run': made['run_id'], 'holder': 'datasets/notes-embedded', 'name': 'notes', 'rows': 6,
                          'dimensions': 8, 'records_run': notes['run_id'], 'current': True, 'problem': None})
        drawn = self.call('embedding_map', {'run': made['run_id'], 'name': 'notes', 'records_run': notes['run_id'],
                                            'colour': 'kind'}, actor=fixtures.EDITOR)
        self.assertEqual((drawn['rows'], drawn['missing'], drawn['method']), (6, 0, 'pca'))
        self.assertEqual([item['name'] for item in drawn['colour']['categories']], ['text', 'image'])
        near = self.call('embedding_neighbours', {'run': made['run_id'], 'name': 'notes',
                                                  'records_run': notes['run_id'], 'record': 'a.txt', 'limit': 2})
        self.assertEqual(len(near['neighbours']), 2)
        self.assertEqual(self.call('embeddings', {'dataset': 'datasets/notes-embedded'})['sets'], [])
        self.assertEqual(self.refused('embeddings', {'dataset': 'nothing'}).code, 'not-found')
        # Built again only when the definition or its input changes.
        self.assertEqual(self.call('plan', {'targets': ['datasets/notes-embedded']})['steps'][-1]['action'], 'built')

    def test_the_machines_embedder_then_the_definitions_model(self):
        self.set_endpoint()
        shown = self.call('endpoint')['embedder']
        self.assertEqual((shown['named_by'], shown['chosen']['model'], shown['prefix']),
                         ('default', 'embeddinggemma-2', 'task: clustering | query: '))
        self.assertEqual(self.refused('set_embedder', {'model': 'writer'}).code, 'not-found')
        self.assertEqual(self.refused('set_embedder', {'model': 'nomic-embed'}, actor=fixtures.EDITOR).code,
                         'forbidden')
        kept = self.call('set_embedder', {'model': 'nomic-embed', 'prefix': 'task: search result | query: '})
        self.assertEqual((kept['named_by'], kept['chosen']['model'], kept['prefix']),
                         ('setting', 'nomic-embed', 'task: search result | query: '))
        self.assertEqual(json.loads(self.settings.read_text())['embedding_model'], 'nomic-embed')
        self.build('datasets/notes-embedded')
        made = self.product('datasets/notes-embedded')
        index = json.loads((Path(made['directory']) / 'embeddings' / 'notes.json').read_text())
        self.assertEqual((index['model']['name'], index['model']['named_by'], index['prefix']),
                         ('nomic-embed', 'setting', 'task: search result | query: '))
        self.assertEqual(index['records'], ['a.txt', 'b.txt', 'c.txt', 'd.txt', 'e.txt'])
        self.assertIn('1 records were not embedded: nomic-embed does not embed image.', index['notes'])
        # The definition's model and prefix come before the machine's.
        self.call('set_embedder', {'model': None})
        self.build('datasets/notes-named')
        made = self.product('datasets/notes-named')
        index = json.loads((Path(made['directory']) / 'embeddings' / 'by-nomic.json').read_text())
        self.assertEqual((index['model']['named_by'], index['prefix']), ('definition', None))
        self.assertEqual(self.posts()[-1]['input']['texts'][0], 'A note about apples.')
        with store.open_project(self.folder) as project:
            rows = project._execute("SELECT operation, outcome, detail FROM {schema}.activity WHERE operation = "
                                    "'set_embedder' ORDER BY at, id").fetchall()
        self.assertEqual([tuple(row[:2]) for row in rows], [('set_embedder', 'not-found'), ('set_embedder', 'done'),
                                                           ('set_embedder', 'done')])

    def test_embeddinggemma_2_not_served_fails_before_anything_is_asked(self):
        self.fake['served_models'] = embedding_listing(gemma=False)
        self.set_endpoint()
        done = self.build('datasets/notes-embedded', ok=False)
        problem = (Path(done['steps'][-1]['directory']) / 'stderr.log').read_text(encoding='utf-8')
        self.assertIn('does not serve EmbeddingGemma 2', problem)
        self.assertIn('nomic-embed (nomic-ai/nomic-embed-text-v1.5-GGUF', problem)
        self.assertEqual(self.posts(), [])

    def test_a_failure_part_way_then_a_build_that_asks_only_for_the_rest(self):
        self.set_endpoint()
        self.fake['modes'] = ['not_admitted', 'success', 'success', 'unknown']
        done = self.build('datasets/notes-embedded', ok=False)
        failed = done['steps'][-1]
        self.assertIn('Batch 3, from the record e.txt, failed', (Path(failed['directory']) / 'stderr.log').read_text())
        self.assertIn('Batch 1 was not admitted', self.stdout(failed))
        self.assertEqual(len(self.posts()), 4)
        first_ids = [body['request_id'] for body in self.posts()]
        self.assertTrue(first_ids[0].endswith(':1:1') and first_ids[1].endswith(':1:2'), first_ids)
        self.fake['requests'].clear()
        done = self.build('datasets/notes-embedded')
        self.assertIn('4 rows were taken from the failed run before', self.stdout(done['steps'][-1]))
        posts = self.posts()
        self.assertEqual([body['input'].get('texts') or len(body['input']['items']) for body in posts],
                         [['task: clustering | query: A note about eels.'], 1])
        made = self.product('datasets/notes-embedded')
        index = json.loads((Path(made['directory']) / 'embeddings' / 'notes.json').read_text())
        self.assertEqual(index['records'], ['a.txt', 'b.txt', 'c.txt', 'd.txt', 'e.txt', 'photo.png'])
        analysis = embeddings.analysis(inside.Product(made['run_id'], made['directory']), 'notes')
        for row, name in enumerate(index['records'][:5]):
            expected = unit(vector_of('task: clustering | query: ' + NOTES[name], 8))
            self.assertLess(max(abs(a - b) for a, b in zip(analysis.row(row), expected)), 1e-6)

    def test_no_endpoint_the_plan_says_so(self):
        self.build('datasets/notes')
        made = self.call('plan', {'targets': ['datasets/notes-embedded']})
        self.assertFalse(made['buildable'])
        self.assertEqual(made['steps'][-1]['blocked_by'][0]['reason'], plan.NO_ENDPOINT_EMBED)

    def test_select_and_freeze_take_exactly_the_records_named(self):
        self.build('datasets/picked')
        made = self.product('datasets/picked')
        listed = fixtures.records_of(made['directory'])
        self.assertEqual([record['id'] for record in listed], ['a.txt', 'c.txt', 'photo.png'])
        self.assertEqual(listed[0]['sha256'], hashlib.sha256(NOTES['a.txt'].encode()).hexdigest())
        self.assertEqual(listed[2]['path'], 'files/photo.png')
        self.assertTrue((Path(made['directory']) / 'files' / 'photo.png').is_file())
        done = self.build('datasets/picked-wrong', ok=False)
        self.assertIn("The record 'nobody.txt' is not in the input",
                      (Path(done['steps'][-1]['directory']) / 'stderr.log').read_text())
        self.build('datasets/notes-frozen')
        frozen = fixtures.records_of(self.product('datasets/notes-frozen')['directory'])
        # a and d are named and accepted; b is named but rejected; c is accepted but not named.
        self.assertEqual(sorted(record['id'] for record in frozen), ['a.txt', 'd.txt'])
        self.assertEqual({record['split'] for record in frozen}, {'train'})


class Published(unittest.TestCase):

    def test_the_seven_are_in_the_project_folder_profile_and_not_in_the_catalog(self):
        names = ('embeddings', 'embedding_map', 'embedding_neighbours', 'embedding_duplicates', 'embedding_outliers',
                 'embedding_leakage', 'set_embedder')
        from tuldok_project import service
        for name in names[1:-1]:
            self.assertEqual((operations.by_name(name).who, operations.by_name(name).mutation), ('inspect', False))
            self.assertIn(name, service.INSIDE_READS)
        self.assertEqual((operations.by_name('set_embedder').who, operations.by_name('set_embedder').mutation),
                         ('owner', True))
        folder = {item['id'] for item in agent_api.capabilities('b' * 32, profile='project_folder')['operations']}
        catalog = agent_api.capabilities('b' * 32)
        self.assertTrue({'project.' + name for name in names} <= folder)
        self.assertFalse({'project.' + name for name in names} & {item['id'] for item in catalog['operations']})
        self.assertEqual((len(catalog['operations']), hashlib.sha256(agent_api.encoded(catalog)).hexdigest()),
                         (110, 'ad5cc7ac91646b39b7a20b9dfca5ec79ed96ded4b5e36732fcf1145f1cc24460'))


if __name__ == '__main__':
    unittest.main()
