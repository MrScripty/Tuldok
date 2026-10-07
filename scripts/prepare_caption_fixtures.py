"""Local design rehearsal using existing owners; NOT an annotated importer.

Run: python scripts/prepare_caption_fixtures.py build/qa/caption-fixture
OUTPUT must not exist. Generated images are authored locally. ZIP extraction
below is restricted to the release this script just produced, not user input.
Target admission and saving are deliberately separate fixture operations; they
do not demonstrate the atomic annotated admission required by the proposal.
"""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from app import Dataset
from dataset_releases import CAPTION_CONSUMER, connected_components
from workbench import WorkbenchError, encode, validate_annotation

CONSUMER = REPO / 'tests/fixtures/diffusion_check_image_data.py'
RATIOS = {'train': 34, 'validation': 33, 'test': 33}
SNAPSHOT_KEYS = ('id', 'kind', 'revision', 'source_revision', 'content_hash',
                 'pixel_hash', 'groups', 'parents', 'source_available',
                 'source_lineage_known', 'source_split', 'source_sha256',
                 'book_id', 'session_id')


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def image_bytes(color, oriented=False, compress_level=6):
    buffer = io.BytesIO()
    image = Image.new('RGB', (512, 768) if oriented else (512, 512), color)
    options = {'compress_level': compress_level}
    if oriented:
        exif = Image.Exif(); exif[274] = 6
        options['exif'] = exif
    image.save(buffer, 'PNG', **options)
    return buffer.getvalue()


def save_caption(dataset, row, caption, review):
    return dataset.workbench.save(row['id'], dict(
        revision=row['revision'], source_revision=row['source_revision'],
        task='image_caption', annotation={'caption': caption}, groups=row['groups'], review=review))


def release_body(rows):
    return dict(format='image_caption_v1', seed=42, ratios=RATIOS,
                items=[{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows])


def extract_authored_release(dataset, release, destination):
    destination.mkdir()
    archive_path = dataset.releases.locate(release['id'])
    assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == release['id']
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            path = Path(name)
            assert not path.is_absolute() and '..' not in path.parts
        archive.extractall(destination)
    return json.loads((destination / 'manifest.json').read_text())


def consumer(root):
    assert hashlib.sha256(CONSUMER.read_bytes()).hexdigest() == CAPTION_CONSUMER['sha256']
    result = subprocess.run([sys.executable, str(CONSUMER), str(root)],
                            capture_output=True, text=True, timeout=20, check=False)
    return {'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}


def origin_tokens(family):
    """Illustrate proposed conservative foreign lineage groups, not a decoder."""
    links = set()
    for row in family:
        links.add('id:' + row['id'])
        links.update('id:' + parent for parent in row['parents'])
        links.update('group:' + group for group in row['groups'])
        if row['source_lineage_known']:
            links.add('legacy:' + ('book:' + row['book_id'] if row['book_id'] else 'session:' + row['session_id']))
    tokens = sorted('caption-origin:' + hashlib.sha256(link.encode('utf-8')).hexdigest() for link in links)
    assert 0 < len(tokens) <= 30  # Existing Workbench contract; larger families need re-planning.
    return tokens


def metadata(root, record):
    path = root / record['export_split'] / 'metadata.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return path, rows, next(i for i, row in enumerate(rows) if row['file_name'] == record['id'] + '.png')


def write_metadata(path, rows):
    path.write_text(''.join(encode(row) + '\n' for row in rows), encoding='utf-8')


def negative_probe(positive, temporary, record, name, mutation, expected_consumer_pass):
    target = temporary / name
    shutil.copytree(positive, target)
    manifest = json.loads((target / 'manifest.json').read_text())
    path, rows, index = metadata(target, record)
    mutation(target, manifest, rows, index)
    write_metadata(path, rows)
    write_json(target / 'manifest.json', manifest)
    result = consumer(target)
    assert (result['exit_code'] == 0) == expected_consumer_pass, (name, result)
    return dict(case=name, existing_consumer=result, future_importer_expected='reject; not implemented')


def main():
    output = Path(sys.argv[1]).resolve()
    if not any(parent in output.parents for parent in (REPO / 'build', REPO / 'output')):
        raise ValueError('Generated fixture output belongs in ignored build/ or output/.')
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='annotated-caption-design-', dir='/tmp') as temporary:
        temporary = Path(temporary)
        source = Dataset(temporary / 'source')
        target = Dataset(temporary / 'target')
        try:
            def add(color, *, parents=None, oriented=False):
                row = source.workbench.import_asset(dict(kind='image',
                    image=base64.b64encode(image_bytes(color, oriented)).decode('ascii'),
                    name=color + '.png', groups=['authored-' + color], parents=parents or [],
                    rights='Locally authored test image; fixture declaration'))
                return save_caption(source, row, 'A ' + color + ' panel.' if color != 'red'
                                    else 'A red panel — pula. 😀', 'human_reviewed')

            deleted = add('purple')
            first = add('red', parents=[deleted['id']], oriented=True)
            second = add('orange', parents=[first['id']])
            bridge = add('gray', parents=[second['id']])
            rows = [first, second, add('green'), add('blue')]
            source.delete(deleted['id'], {'revision': source.sample(deleted['id'])['revision']})
            rows = [source.workbench.get(row['id']) for row in rows]
            release = source.releases.create(release_body(rows))
            assert source.releases.create(release_body(rows))['id'] == release['id']
            positive = output / 'native-caption-release'
            manifest = extract_authored_release(source, release, positive)
            first_consumer = consumer(positive)
            assert first_consumer['exit_code'] == 0, first_consumer
            roots = connected_components([row for family in manifest['protected_components'].values() for row in family])
            for group, family in manifest['protected_components'].items():
                assert len({roots[row['id']] for row in family}) == 1
                assert group == 'component:' + hashlib.sha256(encode(sorted(row['id'] for row in family)).encode()).hexdigest()
            family = manifest['protected_components'][next(r for r in manifest['records'] if r['id'] == first['id'])['export_group']]
            assert deleted['id'] in {r['id'] for r in family if not r['source_available']}
            assert bridge['id'] in {r['id'] for r in family} and bridge['id'] not in {r['id'] for r in manifest['records']}

            mappings, drafts = [], []
            for record in manifest['records']:
                _, projection, index = metadata(positive, record)
                assert projection[index]['text'] == record['annotation']['caption']
                assert projection[index]['group'] == record['export_group']
                family = manifest['protected_components'][record['export_group']]
                assert next(r for r in family if r['id'] == record['id']) == {key: record[key] for key in SNAPSHOT_KEYS}
                raw = (positive / record['asset']).read_bytes()
                observed_hash = hashlib.sha256(raw).hexdigest()
                assert observed_hash == record['asset_sha256'] == record['content_hash']
                groups = origin_tokens(family)
                acquisition = {'format': 'image_caption_v1',
                    'observed': {'asset_sha256': observed_hash},
                    'declared': {'record': copy.deepcopy(record), 'protected_component': copy.deepcopy(family)}}
                # Fixture rehearsal uses existing image owner with explicit split,
                # then existing caption save. Future production admission MUST
                # commit asset + caption + draft history in one owner transaction.
                admitted = target.add(dict(image=base64.b64encode(raw).decode('ascii'),
                    filename=record['id'] + '.png', session_id=groups[0], book_id='', split=record['split']),
                    enrollment=(groups, [], 'unknown', acquisition))
                draft = save_caption(target, target.workbench.get(admitted['id']), projection[index]['text'], 'draft')
                assert draft['id'] != record['id'] and draft['review'] == 'draft' and draft['parents'] == []
                assert draft['source_sha256'] == observed_hash
                assert draft['pixel_hash'] == record['exported_pixel_sha256']
                assert draft['source_split'] == record['split']
                assert draft['provenance']['rights'] == 'unknown'
                assert validate_annotation('image_caption', draft['annotation'], draft) == record['annotation']
                mappings.append(dict(origin_record_id=record['id'], local_record_id=draft['id'],
                    origin_source_sha256=record['source_sha256'], imported_source_sha256=draft['source_sha256'],
                    origin_pixel_sha256=record['pixel_hash'], imported_pixel_sha256=draft['pixel_hash'],
                    split=draft['source_split'], local_groups=groups,
                    annotation=draft['annotation'], review=draft['review']))
                drafts.append(draft)
            assert any(m['origin_source_sha256'] != m['imported_source_sha256'] for m in mappings)
            try:
                target.releases.create(release_body(drafts))
                raise AssertionError('Draft imported captions unexpectedly exported')
            except WorkbenchError as error:
                draft_blocker = str(error)
                assert 'human-reviewed' in draft_blocker
            # This is a test state transition, not a claim of actual human acceptance.
            accepted = [save_caption(target, row, row['annotation']['caption'], 'human_reviewed') for row in drafts]
            second_release = target.releases.create(release_body(accepted))
            second_manifest = extract_authored_release(target, second_release, output / 'reexport-after-fixture-review')
            second_consumer = consumer(output / 'reexport-after-fixture-review')
            assert second_consumer['exit_code'] == 0, second_consumer
            projection = lambda m: sorted((r['exported_pixel_sha256'], r['annotation']['caption'], r['split']) for r in m['records'])
            assert projection(manifest) == projection(second_manifest)

            # Consumer is authoritative for training shape, not admission integrity.
            chosen = next(record for record in manifest['records'] if record['id'] == first['id'])
            def change_text(root, m, rows, i): rows[i]['text'] = ''
            def extra_review(root, m, rows, i): rows[i]['review'] = 'human_reviewed'
            def path_escape(root, m, rows, i):
                shutil.move(root / chosen['asset'], root / 'escaped.png')
                rows[i]['file_name'] = '../escaped.png'
            def changed_hash(root, m, rows, i): m['records'][0]['asset_sha256'] = '0' * 64
            def changed_caption(root, m, rows, i): rows[i]['text'] = 'Unrelated replacement caption.'
            def too_long(root, m, rows, i): rows[i]['text'] = 'x' * 4001
            def crossed_group(root, m, rows, i):
                other = next(r for r in m['records'] if r['split'] != chosen['split'])
                rows[i]['group'] = other['export_group']
            cases = [negative_probe(positive, temporary, chosen, name, mutation, passed)
                     for name, mutation, passed in (
                         ('empty-caption', change_text, False),
                         ('cross-split-group', crossed_group, False),
                         ('forged-review-field', extra_review, True),
                         ('path-escape', path_escape, True),
                         ('manifest-hash-mismatch', changed_hash, True),
                         ('manifest-caption-mismatch', changed_caption, True),
                         ('caption-over-4000', too_long, True))]
            report = dict(base_head='7c43e9b8fe6ff23d3e75d356361fe616c8365d9c',
                consumer=CAPTION_CONSUMER, source_release_id=release['id'],
                reexport_release_id=second_release['id'], selected_records=len(rows),
                complete_family_members=len(manifest['protected_components'][chosen['export_group']]),
                draft_release_blocker=draft_blocker,
                source_consumer=first_consumer, reexport_consumer=second_consumer,
                mappings=mappings, malformed_probes=cases,
                limits='Existing-owner fixture rehearsal; no HTTP/browser/importer/atomic target admission acceptance')
            write_json(output / 'rehearsal-results.json', report)
            print(json.dumps({'fixture_root': str(output), 'records': len(rows),
                              'malformed_probes': len(cases), 'consumer_runs_passed': 2,
                              'draft_export_blocked': True}, indent=2))
        finally:
            target.close()
            source.close()


if __name__ == '__main__':
    main()
