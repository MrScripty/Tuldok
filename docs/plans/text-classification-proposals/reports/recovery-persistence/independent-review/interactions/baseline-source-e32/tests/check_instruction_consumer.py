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


def qualify(path):
    pins = json.loads((Path(__file__).parent / 'instruction-consumer-pins.json').read_text())
    for name, version in pins['versions'].items():
        assert importlib.metadata.version(name) == version, (name, version)
    for filename, expected in pins['sources'].items():
        module = importlib.import_module(filename[:-3].replace('/', '.'))
        assert hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() == expected, filename
    from datasets import load_dataset, Features, Value, disable_progress_bars
    from tokenizers import Tokenizer, models, pre_tokenizers, decoders
    from transformers import PreTrainedTokenizerFast, GPT2Config, GPT2LMHeadModel
    from trl import SFTConfig, SFTTrainer
    disable_progress_bars()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='instruction-consumer-') as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(path) as archive:
            assert len(archive.namelist()) == len(set(archive.namelist()))
            manifest = json.loads(archive.read('manifest.json'))
            assert manifest['format'] == 'text_instruction_v1' and manifest['schema_version'] == 1
            mapping = [json.loads(line) for line in archive.read('rows.jsonl').splitlines()]
            prompts = {row['id']: row for row in manifest['prompts']}
            answers = {row['id']: row for row in manifest['responses']}
            assert len(answers) == len(mapping) == manifest['split_report']['example_count']
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
                    assert pair['split'] == split and prompt['id'] in {member['id'] for member in manifest['protected_components'][pair['family']]}
                    assert row == {'prompt': prompt['text'], 'completion': answer['completion']}
                if rows:
                    dest = root / (split + '.jsonl'); dest.write_bytes(content); data_files[split] = str(dest); expected_splits[split] = rows
            assert mapped == set(answers) and 'train' in data_files
        data = load_dataset('json', data_files=data_files, features=Features({'prompt': Value('string'), 'completion': Value('string')}), cache_dir=str(root / 'cache'))
        for split, rows in expected_splits.items():
            assert list(data[split]) == rows, 'The unchanged JSON consumer must preserve exact Unicode/whitespace'
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
    arguments = parser.parse_args(); result = qualify(arguments.archive)
    if arguments.report: arguments.report.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))
