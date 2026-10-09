"""Bounded human-authored simple polygon targets; no raster/model authority."""
from fractions import Fraction
import math

from workbench import WorkbenchError, text_value

TASK = 'image_segmentation'
MAX_INSTANCES = 100
MAX_VERTICES = 128
MAX_TOTAL_VERTICES = 1024
MAX_RECORDS = 100
MAX_PIXELS = 100_000_000
MAX_BYTES = 40 * 1024 * 1024
BASE_COORDINATES = ('Oriented image pixel-edge xywh; text spans are NFC/LF Unicode code-point [start,end). '
    'Sequence bundles preserve original named staggered fields and accepted intervals; each whole trajectory is indivisible. '
    'Static mesh bundles preserve native xyz/topology and declared units/frame; each whole mesh is indivisible.')
COORDINATES = BASE_COORDINATES + (' Polygon instances retain single simple implicitly closed pixel-edge rings; '
    'bbox and area are continuous bounds and shoelace area, separate from consumer raster quantization.')


def present(rows):
    return any(row['task'] == TASK for row in rows)


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def intersects(a, b, c, d):
    def on(p, q, r):
        return cross(p, q, r) == 0 and all(min(p[i], q[i]) <= r[i] <= max(p[i], q[i]) for i in (0, 1))
    ab_c, ab_d, cd_a, cd_b = cross(a,b,c), cross(a,b,d), cross(c,d,a), cross(c,d,b)
    return ((ab_c * ab_d < 0 and cd_a * cd_b < 0)
            or on(a,b,c) or on(a,b,d) or on(c,d,a) or on(c,d,b))


def geometry(points):
    # Exact predicates over the supplied binary floats/integers, without epsilon.
    rational = [tuple(Fraction(v) for v in point) for point in points]
    twice = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(rational, rational[1:]+rational[:1]))
    try:
        area = float(abs(twice)/2)
    except OverflowError:
        area = math.inf
    if not math.isfinite(area) or area <= 0:
        raise WorkbenchError('Polygon area must be representable as a finite positive number.')
    xs, ys = zip(*points)
    return [min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)], area, rational


def validate(value, record):
    if set(value) != {'instances'} or not isinstance(value['instances'], list) or len(value['instances']) > MAX_INSTANCES:
        raise WorkbenchError('Provide instances, at most 100; an explicitly reviewed empty list means a segmentation negative.')
    instances, identities, total = [], set(), 0
    for instance in value['instances']:
        if not isinstance(instance, dict) or set(instance) != {'label', 'points'}:
            raise WorkbenchError('Polygon instances require exactly label and points.')
        label = text_value(instance['label'], 'Instance label', 80)
        points = instance['points']
        if not isinstance(points, list) or not 3 <= len(points) <= MAX_VERTICES:
            raise WorkbenchError('A polygon requires 3–128 vertices; closure is implicit.')
        total += len(points)
        if total > MAX_TOTAL_VERTICES:
            raise WorkbenchError('A record supports at most 1,024 polygon vertices in total.')
        for point in points:
            try:
                finite = (isinstance(point, list) and len(point) == 2
                          and all(type(v) in (int,float) and math.isfinite(v) for v in point))
            except OverflowError:
                finite = False
            if not finite:
                raise WorkbenchError('Polygon vertices must be finite numeric [x,y] pairs.')
            if not 0 <= point[0] <= record['width'] or not 0 <= point[1] <= record['height']:
                raise WorkbenchError('Polygon vertices must fit oriented image pixel edges.')
        _, _, rational = geometry(points)
        if len(set(rational)) != len(rational):
            raise WorkbenchError('Polygon vertices must be distinct; do not repeat the closing vertex.')
        n = len(points)
        for i, b in enumerate(rational):
            a,c = rational[i-1],rational[(i+1)%n]
            if cross(a,b,c) == 0 and sum((a[k]-b[k])*(c[k]-b[k]) for k in (0,1)) > 0:
                raise WorkbenchError('Polygon adjacent edges must not backtrack or overlap.')
            for j in range(i+1,n):
                if j == i+1 or (i == 0 and j == n-1):
                    continue
                if intersects(b,rational[(i+1)%n],rational[j],rational[(j+1)%n]):
                    raise WorkbenchError('A polygon must be simple; edges must not cross or touch other edges.')
        # A ring has one lexicographically smallest vertex. Compare both orders;
        # Fraction treats 1/1.0 and signed zero equally without rewriting evidence.
        pivot = rational.index(min(rational))
        forward = tuple(rational[pivot:]+rational[:pivot])
        reverse = (forward[0], *reversed(forward[1:]))
        identity = (label,min(forward,reverse))
        if identity in identities:
            raise WorkbenchError('Duplicate same-label polygon instances are not allowed.')
        identities.add(identity)
        instances.append({'label':label,'points':[list(point) for point in points]})
    return {'instances':instances}


def targets(row):
    return row['annotation']['instances' if row['task'] == TASK else 'boxes']


def coco_target(target, task, identifier, image_id, category_id):
    result = dict(id=identifier,image_id=image_id,category_id=category_id,iscrowd=0)
    if task == TASK:
        bbox,area,_ = geometry(target['points'])
        result.update(segmentation=[[v for point in target['points'] for v in point]],bbox=bbox,area=area)
    else:
        result.update(bbox=[target[k] for k in ('x','y','width','height')],area=target['width']*target['height'])
    return result


def selection_bounds(rows):
    if len(rows) > MAX_RECORDS:
        raise WorkbenchError('Segmentation-bearing releases support at most 100 selected records.')
    if sum(row['width']*row['height'] for row in rows if row['kind'] == 'image') > MAX_PIXELS:
        raise WorkbenchError('Segmentation-bearing releases support at most 100 million selected image pixels.')
