"""Small offline production recipes; no model/quality claims or external calls."""
import base64
import io
import random
from PIL import Image, ImageDraw
from workbench import WorkbenchError

RECIPES = {
    'rectangles-v1': {'kind': 'image', 'task': 'image_detection', 'description': 'Known colored rectangles; rendered pixel-edge boxes, including empty scenes. No real-world transfer claim.'},
    'intent-requests-v1': {'kind': 'text', 'task': 'text_classification', 'description': 'Authored scheduling-request grammar; template families are protected. Labels describe the template intent, not a language-model judgment.'},
}

TEMPLATES = (
    ('create', 'Please schedule {topic} on {day} at {hour}.'),
    ('create', 'Add {topic} to my calendar for {day}, {hour}.'),
    ('create', 'I need a new appointment for {topic}: {day} at {hour}.'),
    ('reschedule', 'Move {topic} to {day} at {hour}.'),
    ('reschedule', 'Change the time of {topic} to {hour} on {day}.'),
    ('reschedule', 'Could {topic} happen on {day} at {hour} instead?'),
    ('cancel', 'Cancel {topic} planned for {day} at {hour}.'),
    ('cancel', 'Remove {topic} from my calendar on {day} at {hour}.'),
    ('cancel', 'I no longer need {topic} scheduled for {day}, {hour}.'),
)


def candidates(recipe, seed, count):
    """Yield bytes/text and targets from one structured source of truth."""
    if recipe not in RECIPES:
        raise WorkbenchError('Unknown procedural recipe.', 'unsupported')
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise WorkbenchError('Seed must be an integer from 0 to 4294967295.')
    if type(count) is not int or not 1 <= count <= 100:
        raise WorkbenchError('Generate 1–100 records per bounded offline batch.')
    for ordinal in range(count):
        rng = random.Random(f'{recipe}:{seed}:{ordinal}')
        if recipe == 'rectangles-v1':
            image = Image.new('RGB', (128, 96), (rng.randrange(20, 60), rng.randrange(20, 60), rng.randrange(20, 60)))
            draw, boxes = ImageDraw.Draw(image), []
            # Disjoint cells prevent occlusion; 0..3 objects supplies known negatives.
            for cell in range(ordinal % 4):
                x, y = cell * 40 + rng.randrange(2, 9), rng.randrange(4, 60)
                width, height = rng.randrange(12, 29), rng.randrange(12, 29)
                label, color = rng.choice((('red', (235, 70, 70)), ('blue', (60, 140, 235)), ('yellow', (235, 205, 60))))
                draw.rectangle((x, y, x + width - 1, y + height - 1), fill=color)
                boxes.append(dict(label=label, x=x, y=y, width=width, height=height))
            output = io.BytesIO(); image.save(output, 'PNG')
            payload = {'kind': 'image', 'name': f'rectangles-{seed}-{ordinal}.png',
                       'image': base64.b64encode(output.getvalue()).decode(),
                       'groups': [f'rectangle-scene:{seed}:{ordinal}']}
            annotation, factors = {'boxes': boxes}, {'canvas': [128, 96], 'objects': len(boxes), 'occlusion': 0}
        else:
            template_index = ordinal % len(TEMPLATES)
            label, template = TEMPLATES[template_index]
            factors = dict(topic=rng.choice(('design review', 'project planning', 'reading group', 'demo', 'studio session')),
                           day=rng.choice(('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')),
                           hour=f'{rng.randrange(8, 19)}:{rng.choice(("00", "15", "30", "45"))}', template=template_index)
            payload = {'kind': 'text', 'name': f'intent-{seed}-{ordinal}', 'text': template.format(**factors),
                       'groups': [f'intent-template:{template_index}']}
            annotation = {'label': label}
        payload['rights'] = 'Original procedural recipe; no external source material.'
        yield payload, annotation, {'method': 'procedural', 'recipe': recipe, 'recipe_version': 1,
            'seed': seed, 'ordinal': ordinal, 'factors': factors, 'rights': payload['rights'],
            'verification': 'Targets derived from authored scene/template state; no human review or real-world quality claim.'}


def generate(workbench, body):
    recipe, seed, count = body.get('recipe'), body.get('seed'), body.get('count')
    # Validate the recipe and materialize only the bounded candidate metadata/bytes.
    batch = list(candidates(recipe, seed, count))
    created, rejected = [], []
    for payload, annotation, provenance in batch:
        try:
            record = workbench.import_asset(payload)
        except ValueError as error:
            # Exact duplicate output is rejected and reported, never counted as useful growth.
            rejected.append({'name': payload['name'], 'reason': str(error)})
            continue
        record = workbench.save(record['id'], dict(revision=record['revision'], source_revision=record['source_revision'],
            groups=record['groups'], task=RECIPES[recipe]['task'], annotation=annotation, review='programmatically_verified'),
            verified_provenance=provenance)
        created.append({'id': record['id'], 'revision': record['revision'], 'source_revision': record['source_revision']})
    return {'created': created, 'rejected': rejected, 'requested': count, 'recipe': recipe, 'seed': seed}
