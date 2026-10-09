#!/usr/bin/env python3
"""Actual pinned DPO preparation/collator, exported strings; no model is constructed."""
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
    pins = json.loads((Path(__file__).parent / 'preference-consumer-pins.json').read_text())
    for name, version in pins['versions'].items():
        assert importlib.metadata.version(name) == version, (name, version)
    for filename, expected in pins['sources'].items():
        module = importlib.import_module(filename[:-3].replace('/', '.'))
        assert hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() == expected, filename
    from datasets import load_dataset, Features, Value, disable_progress_bars
    from tokenizers import Tokenizer, models, pre_tokenizers, decoders
    from transformers import PreTrainedTokenizerFast
    from trl import DPOConfig, DPOTrainer
    from trl.trainer.dpo_trainer import DataCollatorForPreference
    disable_progress_bars()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='preference-consumer-') as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(path) as archive:
            assert len(archive.namelist()) == len(set(archive.namelist()))
            manifest = json.loads(archive.read('manifest.json'))
            assert manifest['format'] == 'text_preference_v1' and manifest['schema_version'] == 1
            mapping = [json.loads(line) for line in archive.read('rows.jsonl').splitlines()]
            prompts = {row['id']: row for row in manifest['prompts']}
            answers = {row['id']: row for row in manifest['responses']}
            judgments = {row['id']: row for row in manifest['judgments']}
            expected_ids = {row['id'] for row in judgments.values() if row['outcome'] in ('left', 'right')}
            excluded = {row['id']: row['reason'] for row in manifest['excluded']}
            assert excluded == {row['id']: row['outcome'] for row in judgments.values() if row['outcome'] in ('tie', 'abstain')}
            assert len(expected_ids) == len(mapping) == manifest['split_report']['example_count']
            data_files, expected_splits, mapped, families = {}, {}, set(), {}
            for prompt in prompts.values():
                content = archive.read('prompts/' + prompt['id'] + '.txt')
                assert content == prompt['text'].encode('utf-8')
                assert hashlib.sha256(content).hexdigest() == prompt['content_hash']
            for split in ('train', 'validation', 'test'):
                filename = split + '/data.jsonl'; content = archive.read(filename)
                rows = [json.loads(line) for line in content.splitlines()]
                assert len(rows) == manifest['split_report']['actual_counts'].get(split, 0)
                for index, row in enumerate(rows):
                    assert set(row) == {'prompt', 'chosen', 'rejected'} and all(isinstance(value, str) for value in row.values())
                    matches = [entry for entry in mapping if entry['file'] == filename and entry['row'] == index]
                    assert len(matches) == 1
                    binding = matches[0]; judgment = judgments[binding['id']]; prompt = prompts[binding['prompt_id']]
                    assert binding['id'] not in mapped; mapped.add(binding['id'])
                    assert judgment['review'] == 'human_reviewed' and not judgment['deleted']
                    for key in ('id', 'revision', 'prompt_id', 'parent_revision', 'source_revision', 'left_id', 'left_revision', 'right_id', 'right_revision'):
                        assert binding[key] == judgment[key]
                    assert judgment['left_id'] != judgment['right_id']
                    assert binding['parent_revision'] == prompt['revision'] and binding['source_revision'] == prompt['source_revision']
                    for side in ('left', 'right'):
                        answer = answers[judgment[side+'_id']]
                        assert answer['revision'] == judgment[side+'_revision'] and answer['prompt_id'] == prompt['id']
                    chosen = judgment[judgment['outcome'] + '_id']
                    rejected = judgment['right_id'] if judgment['outcome'] == 'left' else judgment['left_id']
                    assert binding['chosen_id'] == chosen and binding['rejected_id'] == rejected
                    assert row == dict(prompt=prompt['text'], chosen=answers[chosen]['completion'], rejected=answers[rejected]['completion'])
                    assert binding['split'] == split and prompt['id'] in {member['id'] for member in manifest['protected_components'][binding['family']]}
                    assert families.setdefault(binding['family'], split) == split
                if rows:
                    dest = root / (split + '.jsonl'); dest.write_bytes(content); data_files[split] = str(dest); expected_splits[split] = rows
            assert mapped == expected_ids
        data = load_dataset('json', data_files=data_files,
                            features=Features({key: Value('string') for key in ('prompt', 'chosen', 'rejected')}), cache_dir=str(root / 'cache'))
        for split, rows in expected_splits.items():
            assert list(data[split]) == rows, 'Actual JSON loader must preserve exact strings'
        vocab = {token: index for index, token in enumerate(['<pad>', '<eos>', '<unk>', *sorted(pre_tokenizers.ByteLevel.alphabet())])}
        local = Tokenizer(models.BPE(vocab=vocab, merges=[], unk_token='<unk>'))
        local.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=False)
        local.decoder = decoders.ByteLevel()
        tokenizer = PreTrainedTokenizerFast(tokenizer_object=local, pad_token='<pad>', eos_token='<eos>', unk_token='<unk>', model_max_length=10**8)
        args = DPOConfig(output_dir=str(root / 'unused'), use_cpu=True, bf16=False, fp16=False, report_to='none',
                         max_length=None, max_prompt_length=None, max_completion_length=None, disable_tqdm=True)
        assert args.max_length is args.max_prompt_length is args.max_completion_length is None
        # Invoke the unchanged preparation owner without Trainer init, model/ref-model or forward.
        preparer = object.__new__(DPOTrainer); preparer.is_vision_model = False
        prepared = {split: preparer._prepare_dataset(dataset, tokenizer, args, split) for split, dataset in data.items()}
        collator = DataCollatorForPreference(pad_token_id=tokenizer.pad_token_id)
        all_examples, lengths = [], []
        for split, rows in expected_splits.items():
            dataset = prepared[split]
            assert len(dataset) == len(rows)
            for index, row in enumerate(rows):
                actual = dataset[index]
                for key in ('prompt', 'chosen', 'rejected'):
                    expected = tokenizer(row[key], add_special_tokens=False)['input_ids']
                    # Pinned DPO appends EOS unconditionally, including when completion already ends in EOS.
                    if key != 'prompt': expected += [tokenizer.eos_token_id]
                    assert actual[key+'_input_ids'] == expected
                    assert tokenizer.decode(expected, skip_special_tokens=False) == row[key] + (tokenizer.eos_token if key != 'prompt' else '')
                lengths.append(len(actual['prompt_input_ids']) + max(len(actual['chosen_input_ids']), len(actual['rejected_input_ids'])))
                all_examples.append(actual)
        batch = collator(all_examples); padding_positions = 0
        for index, example in enumerate(all_examples):
            for key in ('prompt', 'chosen', 'rejected'):
                ids = batch[key+'_input_ids'][index].tolist(); mask = batch[key+'_attention_mask'][index].tolist()
                expected = example[key+'_input_ids']; padding = len(ids) - len(expected); padding_positions += padding
                expected_ids = ([tokenizer.pad_token_id]*padding + expected if key == 'prompt' else expected + [tokenizer.pad_token_id]*padding)
                expected_mask = ([0]*padding + [1]*len(expected) if key == 'prompt' else [1]*len(expected) + [0]*padding)
                assert ids == expected_ids and mask == expected_mask
                if key != 'prompt': assert expected[-1] == tokenizer.eos_token_id
        assert padding_positions > 0, 'Qualification fixture must observe padding'
        assert max(lengths) > 1024, 'Qualification fixture must cross default max_length'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
        return {'result': 'PASS', 'zip_sha256': before, 'versions': pins['versions'], 'source_hashes': pins['sources'],
                'examples': len(all_examples), 'unique_prompts': len({row['prompt'] for rows in expected_splits.values() for row in rows}),
                'split_counts': {split: len(rows) for split, rows in expected_splits.items()}, 'excluded': excluded,
                'preprocessing': 'Unchanged DPOTrainer._prepare_dataset (prompt extraction, chat dispatch, tokenize_row)',
                'collator': 'Unchanged DataCollatorForPreference; prompt left padding, completions right padding, exact masks',
                'eos': 'Appends EOS unconditionally; an existing terminal EOS becomes two; frozen strings unchanged',
                'truncation': 'max_length/max_prompt_length/max_completion_length=None; all IDs match full strings',
                'max_tokens_observed': max(lengths), 'padding_positions': padding_positions,
                'model': 'No model constructed, no forward/inference/training/pretrained download', 'offline': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('archive', type=Path); parser.add_argument('--report', type=Path)
    arguments = parser.parse_args(); result = qualify(arguments.archive)
    if arguments.report: arguments.report.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))
