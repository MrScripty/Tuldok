#!/usr/bin/env python3
"""Prepare, but never apply, the caption/classification HTML composition.

Call again with the parent's final caption SHA. Refuse an unexamined change
outside the caption panel. No git refs, index, worktree or remote are modified.
"""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess

BASE = '07ec464ba050cd532a2508ce86570a1ce9bcd394'
CLASSIFICATION = '12b174f7a7b2fd6aa36d71da450ad657a5443114'
REPO = Path('/workspace/Tuldok')

def blob(ref):
    return subprocess.check_output(['git', 'show', ref + ':static/workbench.html'], cwd=REPO).decode('utf-8')

def panel(html, identity):
    matches = list(re.finditer(r'<details id="' + re.escape(identity) + r'".*?</details>', html, flags=re.S))
    if len(matches) != 1:
        raise ValueError('Expected exactly one panel: ' + identity)
    return matches[0].group()

class Structure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.scripts = []
        self.forms = []
        self.form_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'script':
            self.scripts.append(attrs.get('src'))
        if tag == 'form':
            if self.form_depth:
                raise ValueError('Nested form')
            self.form_depth += 1
            self.forms.append(attrs.get('id'))

    def handle_endtag(self, tag):
        if tag == 'form':
            if not self.form_depth:
                raise ValueError('Unexpected form close')
            self.form_depth -= 1

def structure(html):
    parsed = Structure()
    parsed.feed(html)
    parsed.close()
    if parsed.form_depth or len(parsed.ids) != len(set(parsed.ids)):
        raise ValueError('Unclosed form or duplicate IDs')
    return parsed

def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--caption-sha', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.caption_sha):
        raise ValueError('Use an exact caption commit SHA')
    base, ours, caption = blob(BASE), blob(CLASSIFICATION), blob(args.caption_sha)
    old, ours_caption, repaired = (panel(h, 'caption-proposal-panel') for h in (base, ours, caption))
    if ours_caption != old:
        raise ValueError('Classification caption panel differs from requested base')
    if caption.replace(repaired, old, 1) != base:
        raise ValueError('Caption HTML has changes outside its panel; inspect them before composition')
    result = ours.replace(old, repaired, 1)
    ours_structure, caption_structure, result_structure = map(structure, (ours, caption, result))
    if set(result_structure.ids) != set(ours_structure.ids) | set(caption_structure.ids):
        raise ValueError('Composition changed the expected ID union')
    if result_structure.scripts != ours_structure.scripts:
        raise ValueError('Classification script order changed')
    for module in ('/caption-proposals.js', '/text-classification-proposals.js'):
        if result_structure.scripts.count(module) != 1:
            raise ValueError('Expected one module script: ' + module)
    if panel(result, 'text-classification-proposal-panel') != panel(ours, 'text-classification-proposal-panel'):
        raise ValueError('Classification panel changed')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {'workbench.resolved.html': result, 'caption.before.html': old,
                 'caption.after.html': repaired,
                 'classification.preserved.html': panel(ours, 'text-classification-proposal-panel')}
    for name, content in artifacts.items():
        (args.output_dir / name).write_text(content)
    receipt = {'classification_sha': CLASSIFICATION, 'original_base': BASE,
               'caption_sha': args.caption_sha, 'status': 'prepared-only, not integrated or published',
               'minimal_change': 'Replace only the caption-proposal-panel with exact caption successor panel',
               'both_feature_panels_preserved': True, 'unique_ids': len(result_structure.ids),
               'forms_non_nested_and_closed': True, 'script_order_unchanged': True,
               'ids_added_by_caption': sorted(set(result_structure.ids) - set(ours_structure.ids)),
               'artifacts_sha256': {name: sha(content) for name, content in artifacts.items()},
               'repo_html_unchanged': blob(CLASSIFICATION) == (REPO / 'static/workbench.html').read_text()}
    if not receipt['repo_html_unchanged']:
        raise ValueError('Repository HTML unexpectedly changed')
    (args.output_dir / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))

if __name__ == '__main__':
    main()
