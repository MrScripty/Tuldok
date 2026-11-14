"""A fake Pumas endpoint for a browser check (tests/browser_project_workspace_endpoint.cjs), driven by lines on stdin.

It starts tests/fake_pumas_typed.py on a loopback port of its own, serving the
listing tests/test_tuldok_project_pumas.py writes (the vision fixture's models,
writer, painter, decider and listener) and advertising itself as 0.8.0, and
prints its address as the first line on stdout. Each line read on stdin is a
JSON object and is answered with one JSON line:

  {"answer": "..."}      the text a suggestion by chat or image_to_text answers
  {"answers": {...}}     the answers a decision gives
  {"modes": [...]}       modes taken one per POST (fake_pumas_typed's)
  {"posts": true}        answers {"posts": [{capability, model, profile, input kind}, ...]}

A text dataset asked by text (generate) is answered "made: <the prompt>", an
image a PNG of the asked size. Nothing else is contacted; it ends with stdin.
"""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fake_pumas_typed  # noqa: E402
from test_tuldok_project_pumas import listing  # noqa: E402


def main():
    server, base, state = fake_pumas_typed.start()
    state['served_models'] = listing()
    state['advertise'] = '0.8.0'
    said = {'answer': 'A short text.', 'answers': {}}

    def respond(body):
        if body['capability'] == 'decision':
            return {'kind': 'decisions', 'answers': said['answers'], 'input_tokens': 7}
        if body['capability'] == 'image_generation':
            from PIL import Image
            out = io.BytesIO()
            Image.new('RGB', (body['options']['width'], body['options']['height']), (35, 95, 160)).save(out, 'PNG')
            import base64
            return {'kind': 'image', 'png_base64': base64.b64encode(out.getvalue()).decode(),
                    'seed': body['options'].get('seed', 7)}
        if body['input'].get('kind') == 'text':
            return {'kind': 'text', 'text': 'made: ' + body['input']['text'], 'finish_reason': 'stop'}
        return {'kind': 'text', 'text': said['answer'], 'finish_reason': 'stop'}

    state['respond'] = respond
    print(base, flush=True)
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            command = json.loads(line)
            if 'answer' in command:
                said['answer'] = command['answer']
            if 'answers' in command:
                said['answers'] = command['answers']
            if 'modes' in command:
                state['modes'] = list(command['modes'])
            if command.get('posts'):
                posts = [{'capability': body.get('capability'), 'model': body.get('model'), 'profile': body.get('profile'),
                          'input': (body.get('input') or {}).get('kind')} for body in state['requests']]
                print(json.dumps({'posts': posts}), flush=True)
            else:
                print(json.dumps({'ok': True}), flush=True)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
