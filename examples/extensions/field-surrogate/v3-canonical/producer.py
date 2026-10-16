"""Canonical scalar A: author-owned numerical training and exact native copies.

This new source version consumes real frozen Release arrays and the captured
SDK. The v2 authored producer and its historical Run remain unchanged.
"""
import hashlib
import io
import json
from pathlib import Path
import resource
import sys
import time
import zipfile

import numpy as np
from tuldok_extension_sdk.evidence import Evidence, progress


def require(value,reason):
    if not value: raise ValueError(reason)


def archive(raw, maximum_entries, maximum_bytes):
    """Bound the complete stored canonical ZIP before consuming any member."""
    import io
    import zipfile
    require(type(raw) is bytes and 22<=len(raw)<=maximum_bytes and raw[:4]==b'PK\x03\x04'
            and raw[-22:-18]==b'PK\x05\x06','Invalid canonical ZIP byte envelope.')
    value=zipfile.ZipFile(io.BytesIO(raw))
    try:
        entries=value.infolist(); names=value.namelist()
        require(0<len(entries)<=maximum_entries and len(set(names))==len(names) and not value.comment
                and entries[0].header_offset==0,'Canonical ZIP count/name/comment differs.')
        require(all(entry.compress_type==zipfile.ZIP_STORED and entry.flag_bits==0
                    and entry.file_size==entry.compress_size and not entry.is_dir()
                    and len(entry.filename)<=512 and '\\' not in entry.filename
                    and all(part not in ('','.','..') for part in entry.filename.split('/')) for entry in entries),
                'Only bounded relative stored canonical files are accepted.')
        require(sum(entry.file_size for entry in entries)<=maximum_bytes,'Expanded ZIP exceeds its bound.')
        return value
    except BaseException:
        value.close();raise


def zip_member(archive_value, name, maximum):
    require(0<archive_value.getinfo(name).file_size<=maximum,'Canonical member exceeds its byte bound.')
    with archive_value.open(name) as stream: raw=stream.read(maximum+1)
    require(len(raw)==archive_value.getinfo(name).file_size and len(raw)<=maximum,'Canonical member length differs.')
    return raw


def main(release_path, derivation_path, provenance_path, context_path, output_path):
    started = time.monotonic(); output = Path(output_path)
    def bounded(path, maximum):
        with Path(path).open('rb') as stream: raw = stream.read(maximum+1)
        if len(raw) > maximum: raise ValueError('Input exceeds explicit bound')
        return raw
    context_raw = bounded(context_path,65536)
    if len(context_raw) > 65536: raise ValueError('Context exceeds explicit bound')
    evidence = Evidence(output, context_raw); policy = evidence.policy
    canonical = policy['canonical']; release_raw = bounded(release_path,1048576)
    derivation_raw = bounded(derivation_path,65536); provenance_raw = bounded(provenance_path,65536)
    for key, raw, limit in (('release', release_raw, 1048576), ('derivation', derivation_raw, 65536), ('provenance', provenance_raw, 65536)):
        if len(raw) > limit or hashlib.sha256(raw).hexdigest() != canonical[key]['sha256']:
            raise ValueError('Exact captured canonical input differs: ' + key)
    if policy['format'] != 'extension_field_policy_v2' or evidence.static['probe']['data_sha256'] != canonical['release']['sha256']:
        raise ValueError('Explicit canonical policy/Release identity differs')
    derivation = json.loads(derivation_raw); provenance = json.loads(provenance_raw)
    if provenance['release_sha256'] != canonical['release']['sha256'] or provenance['contract'] != canonical['contract']:
        raise ValueError('Exact author compilation provenance differs')
    cases = {}; members = {row['case_id']: row for row in canonical['members']}
    with archive(release_raw,72,1048576) as frozen_archive:
        frozen = {row['id']: row for row in json.loads(zip_member(frozen_archive,'manifest.json',65536))['records']}
        for case in derivation['cases']:
            selected_member = members[case['id']]; row = frozen[selected_member['record_id']]
            if any(row[key] != selected_member[key] for key in ('revision', 'source_revision', 'split')):
                raise ValueError('Frozen canonical member changed')
            with archive(zip_member(frozen_archive,row['asset'],262144),64,262144) as bundle:
                source = json.loads(zip_member(bundle,'manifest.json',65536))
                arrays = {item['field']: item for item in source['frames'][case['frame']]['arrays']}
                values = {}
                for item in case['arrays']:
                    raw = zip_member(bundle,arrays[item['field_id']]['path'],8192)
                    if len(raw) > 8192 or hashlib.sha256(raw).hexdigest() != item['source_sha256']:
                        raise ValueError('Native source identity differs')
                    array = np.load(io.BytesIO(raw), allow_pickle=False)
                    if array.dtype.str != '<f8' or array.shape != (4,4,4) or not np.isfinite(array).all():
                        raise ValueError('Native source field differs')
                    values[item['field_id']] = array.reshape(-1)
                    evidence.write_raw(item['output']['name'], raw)
                cases[case['id']] = dict(split=row['split'], **values)
    evidence.write_raw(canonical['derivation']['output'], derivation_raw)
    fit = [member['member_id'] for member in policy['fit_members']]
    if fit != derivation['fit_case_ids'] or any(cases[key]['split'] != 'train' for key in fit):
        raise ValueError('Fit population differs')
    train_x = np.concatenate([cases[key]['initial'] for key in fit])
    train_y = np.concatenate([cases[key]['reference'] for key in fit])
    mean = float(np.mean(train_x)); std = float(np.sqrt(np.mean((train_x-mean)**2)))
    if not np.isfinite(std) or std <= 0: raise ValueError('Training-only variance must be positive')
    x = (train_x-mean)/std
    def save(name, values):
        with (output/name).open('xb') as handle: np.save(handle,np.ascontiguousarray(values,dtype='<f8'),allow_pickle=False)
    save('transform.npy',[mean,std]); evidence.transform('transform.npy')
    rate = evidence.static['parameters']['learning_rate']; updates = evidence.static['parameters']['updates']
    configuration = policy['model_specification']['configuration']
    a = float(configuration['initial_scale']); b = float(configuration['initial_offset']); observations = []
    for update in range(1,updates+1):
        residual = a*x+b-train_y
        a -= rate*2*float(np.mean(residual*x)); b -= rate*2*float(np.mean(residual))
        if update % 16: continue
        save(f'weights-{update}.npy',[a,b]); mse=[]
        for member in evidence.static['probe']['members']:
            key = member['frozen_reference']['member_id']; case = cases[key]
            if case['split'] != 'validation' or key in fit: raise ValueError('Probe population differs')
            prediction = a*((case['initial']-mean)/std)+b
            if not np.isfinite(prediction).all(): raise ValueError('Nonfinite prediction')
            binding = next(row for row in policy['field_outputs'] if row['clock']==update and row['member_id']==key)
            save(binding['prediction'],prediction.reshape((4,4,4)))
            mse.append(float(np.mean((prediction-case['reference'])**2)))
        clocks = dict(optimizer_update=update,epoch=None,fit_pass=None,physical_time=None,
                      wall_elapsed_ms=int((time.monotonic()-started)*1000))
        evidence.checkpoint(update,clocks,f'weights-{update}.npy',{'reference_mse':float(np.mean(mse))})
        observations.append(dict(optimizer_update=update,reference_mse=float(np.mean(mse))))
        print(progress('train',update,updates,{'reference_mse':float(np.mean(mse))}),flush=True)
    evidence.write('diagnostics.json',dict(format='extension_scalar_canonical_training_v1',fit_member_ids=fit,
        learning_rate=rate,updates=updates,observations=observations,release_sha256=canonical['release']['sha256']))
    evidence.finish()
    print(json.dumps(dict(cost=dict(main_elapsed_seconds=time.monotonic()-started,
        process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)),allow_nan=False),flush=True)


if __name__ == '__main__':
    if len(sys.argv) != 6: raise SystemExit('Use producer.py RELEASE DERIVATION PROVENANCE HOST_CONTEXT OUTPUT_DIRECTORY')
    main(*sys.argv[1:])
