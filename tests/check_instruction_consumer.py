#!/usr/bin/env python3
"""Qualify an actual instruction ZIP with unchanged pinned public CPU consumers."""
import os
os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_DATASETS_OFFLINE='1')
import argparse
import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path
import tempfile
import zipfile


def check_families(manifest, mapping):
    """Check the complete supplied snapshot graph, without claiming DB authenticity."""
    graph = {}
    def root(key):
        graph.setdefault(key, key)
        while graph[key] != key:
            graph[key] = graph[graph[key]]; key = graph[key]
        return key
    def join(a, b):
        graph[root(b)] = root(a)
    snapshots, owners = {}, {}
    for family, members in manifest['protected_components'].items():
        assert isinstance(members, list) and members
        for member in members:
            assert member['id'] not in snapshots
            snapshots[member['id']] = member; owners[member['id']] = family
            key = 'id:' + member['id']
            links = ['group:' + group for group in member['groups']] + ['id:' + parent for parent in member['parents']]
            if member['content_hash']: links.append('content:' + member['kind'] + ':' + member['content_hash'])
            if member['pixel_hash']: links.append('pixels:' + member['pixel_hash'])
            if member['kind'] == 'image' and member['source_lineage_known']:
                links.append('legacy:' + ('book:' + member['book_id'] if member['book_id'] else 'session:' + member['session_id']))
            root(key)
            for link in links: join(key, link)
    roots = {}
    for family, members in manifest['protected_components'].items():
        components = {root('id:' + member['id']) for member in members}
        assert len(components) == 1, 'Declared family must be connected in the supplied relationship graph'
        component = components.pop(); assert component not in roots, 'Related families cannot be divided'
        roots[component] = family
    prompts = {row['id']: row for row in manifest['prompts']}
    for row in [*prompts.values(), *manifest.get('grounded_sources', [])]:
        snapshot = snapshots[row['id']]
        assert all(row[key] == value for key, value in snapshot.items()), 'Frozen source/prompt snapshot must match family evidence'
    family_splits, prompt_splits = {}, {}
    for pair in mapping:
        family, split = pair['family'], pair['split']; prompt = prompts[pair['prompt_id']]
        assert split in ('train', 'validation', 'test') and owners[prompt['id']] == family
        assert all(owners[parent] == family for parent in prompt['parents'])
        assert family_splits.setdefault(family, split) == split, 'One family cannot leak across splits'
        assert prompt_splits.setdefault(prompt['id'], split) == split, 'One prompt cannot leak across splits'
        fixed = {member['source_split'] for member in manifest['protected_components'][family] if member['source_split'] != 'unassigned'}
        assert len(fixed) <= 1 and (not fixed or fixed == {split}), 'Inherited fixed source splits must be preserved'


def qualify(path, *, reader_only=False):
    pins = json.loads((Path(__file__).parent / 'instruction-consumer-pins.json').read_text())
    for name, version in pins['versions'].items():
        assert importlib.metadata.version(name) == version, (name, version)
    for filename, expected in pins['sources'].items():
        source = importlib.metadata.distribution(filename.split('/')[0]).locate_file(filename)
        assert hashlib.sha256(Path(source).read_bytes()).hexdigest() == expected, filename
    from datasets import load_dataset, Features, Value, disable_progress_bars
    disable_progress_bars()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='instruction-consumer-') as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(path) as archive:
            assert len(archive.namelist()) == len(set(archive.namelist()))
            assert sum(member.file_size for member in archive.infolist()) <= 40*1024*1024
            manifest = json.loads(archive.read('manifest.json'))
            assert manifest['format'] == 'text_instruction_v1' and manifest['schema_version'] == 1
            mapping = [json.loads(line) for line in archive.read('rows.jsonl').splitlines()]
            prompts = {row['id']: row for row in manifest['prompts']}
            answers = {row['id']: row for row in manifest['responses']}
            contexts = {row['id']: row for row in manifest.get('grounded_sources', [])}
            assert len(contexts) == len(manifest.get('grounded_sources', []))
            canonical = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
            for source in contexts.values():
                content = archive.read('contexts/' + source['id'] + '.txt')
                assert source['kind'] == 'text' and source['source_available']
                assert content == source['text'].encode('utf-8')
                assert hashlib.sha256(content).hexdigest() == source['content_hash']
            for prompt in prompts.values():
                recipe = prompt['provenance'].get('grounded_instruction')
                if not recipe:
                    continue
                assert recipe['schema'] == 'tuldok_grounded_instruction_v1'
                captured = prompt['grounded_context_binding']
                assert 2 <= len(captured) <= 4 and len({item['ref']['id'] for item in captured}) == len(captured)
                assert len(recipe['question']) <= 4000
                assert len(recipe['creation_contexts']) == len(captured)
                for original, item in zip(recipe['creation_contexts'], captured):
                    ref = item['ref']; source = contexts[ref['id']]
                    for key in ('id', 'content_hash', 'start', 'end', 'quote'):
                        assert original['ref'][key] == ref[key]
                    assert ref['id'] in prompt['parents']
                    for key in ('id', 'revision', 'source_revision', 'content_hash'):
                        assert ref[key] == source[key]
                    assert type(ref['start']) is int and type(ref['end']) is int
                    assert 0 <= ref['start'] < ref['end'] <= len(source['text']) and ref['end']-ref['start'] <= 10000
                    assert source['text'][ref['start']:ref['end']] == ref['quote']
                    assert item['source_metadata'] == {key: source[key] for key in ('name', 'groups', 'parents', 'provenance', 'review', 'task')}
                expected = '\n\n'.join(f"Source {i} [{item['ref']['id']}]\n{item['ref']['quote']}" for i, item in enumerate(captured, 1)) + '\n\nQuestion\n' + recipe['question']
                assert prompt['text'] == expected
                digest = hashlib.sha256(canonical(dict(parent_revision=prompt['revision'], contexts=captured)).encode()).hexdigest()
                for answer in answers.values():
                    if answer['prompt_id'] == prompt['id']:
                        assert answer['grounded_binding_sha256'] == digest and len(answer['completion']) <= 20000
            assert len(answers) == len(mapping) == manifest['split_report']['example_count']
            check_families(manifest, mapping)
            data_files, expected_splits, mapped = {}, {}, set()
            for prompt in prompts.values():
                content = archive.read('prompts/' + prompt['id'] + '.txt')
                assert content == prompt['text'].encode('utf-8')
                assert hashlib.sha256(content).hexdigest() == prompt['content_hash']
            for split in ('train', 'validation', 'test'):
                filename = split + '/data.jsonl'; content = archive.read(filename)
                rows = [json.loads(line) for line in content.splitlines()]
                assert len(rows) == manifest['split_report']['actual_counts'].get(split, 0)
                for index, row in enumerate(rows):
                    assert set(row) == {'prompt', 'completion'} and all(isinstance(value, str) for value in row.values())
                    matches = [entry for entry in mapping if entry['file'] == filename and entry['row'] == index]
                    assert len(matches) == 1
                    pair = matches[0]; answer = answers[pair['id']]; prompt = prompts[pair['prompt_id']]
                    assert pair['id'] not in mapped; mapped.add(pair['id'])
                    assert pair['revision'] == answer['revision'] and answer['review'] == 'human_reviewed'
                    assert answer['prompt_id'] == prompt['id'] and pair['parent_revision'] == prompt['revision'] and pair['source_revision'] == prompt['source_revision']
                    if prompt.get('grounded_context_binding'):
                        members = {member['id'] for member in manifest['protected_components'][pair['family']]}
                        assert all(item['ref']['id'] in members for item in prompt['grounded_context_binding'])
                    assert pair['split'] == split and prompt['id'] in {member['id'] for member in manifest['protected_components'][pair['family']]}
                    assert row == {'prompt': prompt['text'], 'completion': answer['completion']}
                if rows:
                    dest = root / (split + '.jsonl'); dest.write_bytes(content); data_files[split] = str(dest); expected_splits[split] = rows
            assert mapped == set(answers) and 'train' in data_files
        data = load_dataset('json', data_files=data_files, features=Features({'prompt': Value('string'), 'completion': Value('string')}), cache_dir=str(root / 'cache'))
        for split, rows in expected_splits.items():
            assert list(data[split]) == rows, 'The unchanged JSON consumer must preserve exact Unicode/whitespace'
        if reader_only:
            assert hashlib.sha256(path.read_bytes()).hexdigest() == before
            return dict(result='PASS', mode='pinned_datasets_json_reader_only', zip_sha256=before,
                        versions=pins['versions'], source_hashes=pins['sources'], examples=len(answers),
                        unique_prompts=len(prompts), context_sources=len(contexts),
                        split_counts={split: len(rows) for split, rows in expected_splits.items()},
                        exact_unicode_and_context_evidence='PASS', models_or_trainers_constructed=False,
                        training=False, quality_claim=False, offline=True)
        from tokenizers import Tokenizer, models, pre_tokenizers, decoders
        from transformers import PreTrainedTokenizerFast, GPT2Config, GPT2LMHeadModel
        from trl import SFTConfig, SFTTrainer
        # Byte BPE with no merges has an exact prefix boundary and complete UTF-8 coverage.
        vocab = {token: index for index, token in enumerate(['<pad>', '<eos>', '<unk>', *sorted(pre_tokenizers.ByteLevel.alphabet())])}
        local = Tokenizer(models.BPE(vocab=vocab, merges=[], unk_token='<unk>'))
        local.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=False)
        local.decoder = decoders.ByteLevel()
        tokenizer = PreTrainedTokenizerFast(tokenizer_object=local, pad_token='<pad>', eos_token='<eos>', unk_token='<unk>', model_max_length=10**8)
        longest = max(len(tokenizer(row['prompt'] + row['completion'] + '<eos>')['input_ids']) for rows in expected_splits.values() for row in rows)
        model = GPT2LMHeadModel(GPT2Config(vocab_size=len(tokenizer), n_positions=max(128, longest+1), n_embd=16, n_layer=1, n_head=2, pad_token_id=tokenizer.pad_token_id, eos_token_id=tokenizer.eos_token_id))
        args = SFTConfig(output_dir=str(root / 'trainer'), use_cpu=True, bf16=False, fp16=False,
                         report_to='none', max_length=None, packing=False, completion_only_loss=True, disable_tqdm=True)
        assert args.max_length is None and not args.packing and args.completion_only_loss
        trainer = SFTTrainer(model=model, args=args, train_dataset=data['train'],
                             eval_dataset={split: dataset for split, dataset in data.items() if split != 'train'} or None,
                             processing_class=tokenizer)
        prepared = {'train': trainer.train_dataset, **(trainer.eval_dataset or {})}
        lengths = []
        for split, rows in expected_splits.items():
            dataset = prepared[split]; assert len(dataset) == len(rows)
            for index, row in enumerate(rows):
                actual = dataset[index]
                completion = row['completion'] if row['completion'].endswith(tokenizer.eos_token) else row['completion'] + tokenizer.eos_token
                expected_ids = tokenizer(row['prompt'] + completion)['input_ids']; prompt_length = len(tokenizer(row['prompt'])['input_ids'])
                assert actual['input_ids'] == expected_ids
                assert tokenizer.decode(actual['input_ids'], skip_special_tokens=False) == row['prompt'] + completion
                assert actual['completion_mask'] == [0]*prompt_length + [1]*(len(expected_ids)-prompt_length)
                lengths.append(len(expected_ids))
            batch = trainer.data_collator([dataset[index] for index in range(len(rows))])
            for index in range(len(rows)):
                actual = dataset[index]; length = len(actual['input_ids'])
                for offset, token in enumerate(actual['input_ids']):
                    assert batch['labels'][index,offset].item() == (token if actual['completion_mask'][offset] else -100)
                assert all(value == -100 for value in batch['labels'][index,length:].tolist())
                assert batch['labels'][index,length-1].item() == tokenizer.eos_token_id
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
        return {'result': 'PASS', 'zip_sha256': before, 'versions': pins['versions'], 'source_hashes': pins['sources'],
                'examples': len(answers), 'unique_prompts': len(prompts), 'split_counts': {split: len(rows) for split, rows in expected_splits.items()},
                'completion_mask_and_padding_labels': 'PASS', 'eos': 'Consumer appends EOS exactly once when absent; canonical archive unchanged',
                'truncation': 'max_length=None, packing=False; token sequences match full input', 'max_tokens_observed': max(lengths),
                'over_default_1024_tokens': any(length > 1024 for length in lengths),
                'model': 'Locally constructed random GPT2, 1 layer/16 hidden; no pretrained download or training',
                'tokenizer': 'Locally constructed complete byte BPE with no merges; exact prefix boundary', 'offline': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('archive', type=Path); parser.add_argument('--report', type=Path)
    parser.add_argument('--reader-only', action='store_true', help='Read exact JSON rows/evidence with pinned Datasets; construct no tokenizer/model/trainer.')
    arguments = parser.parse_args(); result = qualify(arguments.archive, reader_only=arguments.reader_only)
    if arguments.report: arguments.report.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))
