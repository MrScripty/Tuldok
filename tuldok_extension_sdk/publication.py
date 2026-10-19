"""Explicit recovered-result collection through the selected public CLI; no compute."""
import hashlib
import os
from pathlib import Path
import shutil
import stat
import time

from .evidence import boundary, canonical, closed, digest, identifier, name, natural, require, sha


@boundary
def result_reference(value):
    closed(value, ('kind', 'schema_version', 'catalog_id', 'run_id', 'material_sha256',
                   'inventory_sha256', 'custody_receipt_sha256', 'sha256'), 'Publication result Ref')
    require(value['kind'] == 'recovered_publication_result' and type(value['schema_version']) is int
            and value['schema_version'] == 1, 'Unsupported publication result Ref.', 'unsupported')
    identifier(value['catalog_id']); identifier(value['run_id'])
    for key in ('material_sha256', 'inventory_sha256', 'custody_receipt_sha256', 'sha256'): sha(value[key])
    return value


def _verify_download(path, item, deadline):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and before.st_nlink == 1
                and before.st_size == item['bytes'], 'Collected publication file identity differs.')
        checksum = hashlib.sha256(); count = 0
        while count < item['bytes']:
            require(time.monotonic() < deadline, 'Publication collection deadline elapsed.', 'unavailable')
            raw = os.read(descriptor, min(65536, item['bytes'] - count))
            require(raw, 'Collected publication file is truncated.')
            count += len(raw); checksum.update(raw)
        after = os.fstat(descriptor); current = path.stat(follow_symlinks=False)
        keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode', 'st_uid', 'st_nlink')
        require(all(getattr(before, key) == getattr(after, key) == getattr(current, key) for key in keys)
                and checksum.hexdigest() == item['sha256'], 'Collected whole publication file changed.')
    finally: os.close(descriptor)


@boundary
def collect(client, ref, output):
    """Download one exact attached inventory; preserve partial files on refusal."""
    result_reference(ref)
    value = client.call('runs.publication_result', {'ref': ref})
    require(type(value) is dict and value.get('result_ref') == ref, 'CLI returned another publication result.')
    document = {key: item for key, item in value.items() if key != 'result_ref'}
    require(digest(document) == ref['sha256'] and all(document.get(key) == ref[key] for key in
        ('catalog_id', 'run_id', 'material_sha256', 'inventory_sha256', 'custody_receipt_sha256')),
        'CLI publication result identity differs.')
    artifacts = document['artifacts']
    require(type(artifacts) is list and len(artifacts) <= 96, 'Publication inventory exceeds its bound.')
    for item in artifacts:
        closed(item, ('name', 'role', 'bytes', 'sha256', 'media_type'), 'Publication artifact')
        name(item['name']); sha(item['sha256']); natural(item['bytes'], 'Artifact bytes', 0, 512*1024**2)
    require(len({item['name'] for item in artifacts}) == len(artifacts), 'Repeated publication artifact.')
    inventory = [{'path': item['name'], **{key: item[key] for key in ('role', 'bytes', 'sha256')}} for item in artifacts]
    require(digest(inventory) == ref['inventory_sha256'], 'Publication inventory hash differs.')
    total = sum(item['bytes'] for item in artifacts)
    require(total <= 4 * 1024**3, 'Publication exceeds the finite collection bound.', 'unsupported')
    output = Path(output).absolute()
    require(not output.exists() and not output.is_symlink(), 'Choose an absent publication collection directory.')
    require(shutil.disk_usage(output.parent).free >= total + 1024**2, 'Insufficient publication collection storage.', 'unavailable')
    output.mkdir(mode=0o700)
    for item in artifacts:
        require(time.monotonic() < client.deadline, 'Publication collection deadline elapsed.', 'unavailable')
        client.download_publication(ref, item, output / item['name'])
        _verify_download(output / item['name'], item, client.deadline)
    require(time.monotonic() < client.deadline, 'Publication collection deadline elapsed.', 'unavailable')
    return {'format': 'extension_sdk_publication_collection_v1', 'state': 'collected', 'result_ref': ref,
            'artifacts': inventory, 'verification': 'whole_sha256_verified', 'numerical': 'not_evaluated'}


@boundary
def compare(client, ref, other_ref, selection):
    """Read exact paired/side-by-side semantics; never select a candidate."""
    result_reference(ref); result_reference(other_ref)
    require(ref['catalog_id'] == other_ref['catalog_id'], 'Choose results from one catalog.', 'unsupported')
    closed(selection, ('checkpoint_sha256', 'other_checkpoint_sha256', 'evaluation_sha256',
        'other_evaluation_sha256', 'metric_id', 'metric_definition_sha256',
        'other_metric_definition_sha256', 'mode'), 'Exact comparison selection')
    for key, value in selection.items():
        if key.endswith('sha256'): sha(value)
    require(selection['mode'] in ('paired', 'side_by_side'), 'Choose paired or side_by_side comparison.')
    value = client.call('runs.compare_publication_evidence', {'ref': ref, 'other_ref': other_ref, 'selection': selection})
    require(type(value) is dict and value.get('result_refs') == [ref, other_ref], 'Comparison returned different results.')
    comparison = value['comparison']
    require(comparison['mode'] == selection['mode'] and len(comparison['sides']) == 2,
            'Comparison returned a different selection.')
    for index, (side, selected_ref) in enumerate(zip(comparison['sides'], (ref, other_ref), strict=True)):
        prefix = 'other_' if index else ''
        require(side['run_id'] == selected_ref['run_id'] and side['metric_id'] == selection['metric_id']
                and all(side[key] == selection[prefix + key] for key in
                    ('checkpoint_sha256', 'evaluation_sha256', 'metric_definition_sha256')),
                'Comparison side differs from its exact selection.')
    require(time.monotonic() < client.deadline, 'Publication comparison deadline elapsed.', 'unavailable')
    return {'format': 'extension_sdk_publication_comparison_v1', 'state': 'compared',
            'result_refs': value['result_refs'], 'comparison': comparison, 'numerical': 'not_evaluated'}
