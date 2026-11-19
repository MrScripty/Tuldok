"""Agreement between annotation sets: per record, per pair of sets, and the most disputed records.

Owns section 5 of docs/plans/training-and-curation/spec-t4.md: how far two
or more sets of one task agree on each record (a number from 0 to 1), the
figures each type also reports (Cohen's and Fleiss' kappa, Kendall's tau,
IoU of matched objects, OKS, identity switches and fragments), the
confidence filter, and the order of the disputed list. It is pure and uses
the standard library alone: values come in as the sets hold them, and the
payload of a mask, a depth map or a point-id file is read through a loader
the caller gives (bytes of a sidecar). Nothing is written.

A set is {record: {'value', 'confidence'?}}. A record's agreement for a pair
is 0 when one side has no annotation of it (or the filter emptied it).
"""
from array import array
import difflib
import itertools
import math

from . import annotation_payloads as payloads

SETS_LIMIT = 8
HUNGARIAN_LIMIT = 64          # objects of one term per side matched exactly; above, greedily
GRID = 128                    # cells across a polygon pair's joint box, at most
TEXT_COMPARED = 4000          # characters of a text compared
OKS_SIGMA = 0.1               # spread of a keypoint (the task may say sigma)
MATCH_IOU = 0.5               # an identity switch follows matches above this IoU; F1 counts them
DEPTH_RATIO = 1.25            # the δ of depth agreement

MEASURES = {
    'class': 'Equal terms score 1. Cohen\'s kappa per pair; Fleiss\' kappa over the records every set annotated.',
    'tags': 'Jaccard of the two sets of terms.',
    'text': 'The similarity of the two texts (difflib ratio of their first 4,000 characters).',
    'ranking': '(τ + 1) / 2, Kendall\'s τ over the candidates both rank.',
    'boxes': 'Matched IoU: boxes of the same term matched one to one; summed IoU over the larger count.',
    'polygons': 'Matched IoU: polygons of the same term matched one to one; summed IoU over the larger count.',
    'box3d': 'Matched IoU: 3-D boxes of the same term matched one to one; summed IoU over the larger count.',
    'points': 'Matched IoU: point objects of the same term matched one to one; summed IoU over the larger count.',
    'mask': 'Instance masks: matched IoU of their objects. Semantic masks: mean pixel IoU over the terms used.',
    'keypoints': 'Matched OKS: instances of the same term matched one to one; summed OKS over the larger count.',
    'depth': '1 − mean |a − b| / mean (|a| + |b|) / 2 over the pixels with depth in both.',
    'spans': 'Mean over the terms used of the interval IoU.',
    'segments': 'Mean over the terms used of the interval IoU.',
    'timeseries': 'Mean over the terms used of the interval IoU.',
    'track': 'Matched track IoU: tracks of the same term matched one to one by their mean box IoU over the frames '
             'either has; summed over the larger count.',
}


class AgreementProblem(Exception):
    """A task or a value that cannot be compared; the message is a sentence."""


# ------------------------------------------------------------- geometry

def box_iou(a, b):
    """IoU of two boxes (x, y, w, h)."""
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def _inside(x, y, polygon):
    """Even-odd rule."""
    hit = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def polygon_iou(a, b):
    """IoU of two polygons drawn on a grid over their joint box: at most GRID cells a side, pixel centres."""
    xs = [p[0] for p in a + b]
    ys = [p[1] for p in a + b]
    x0, y0, x1, y1 = math.floor(min(xs)), math.floor(min(ys)), math.ceil(max(xs)), math.ceil(max(ys))
    step = max(1.0, max(x1 - x0, y1 - y0) / GRID)
    both = either = 0
    y = y0 + step / 2
    while y < y1:
        x = x0 + step / 2
        while x < x1:
            in_a, in_b = _inside(x, y, a), _inside(x, y, b)
            both += in_a and in_b
            either += in_a or in_b
            x += step
        y += step
    return both / either if either else 0.0


def _corners(centre, size, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    half = ((size[0] / 2, size[1] / 2), (-size[0] / 2, size[1] / 2), (-size[0] / 2, -size[1] / 2),
            (size[0] / 2, -size[1] / 2))
    return [(centre[0] + c * dx - s * dy, centre[1] + s * dx + c * dy) for dx, dy in half]


def _clip(subject, edge_a, edge_b):
    """Sutherland-Hodgman: subject clipped by the half plane left of edge a -> b."""
    def left(p):
        return (edge_b[0] - edge_a[0]) * (p[1] - edge_a[1]) - (edge_b[1] - edge_a[1]) * (p[0] - edge_a[0]) >= 0

    def cross(p, q):
        dx1, dy1 = q[0] - p[0], q[1] - p[1]
        dx2, dy2 = edge_b[0] - edge_a[0], edge_b[1] - edge_a[1]
        denominator = dx1 * dy2 - dy1 * dx2
        t = ((edge_a[0] - p[0]) * dy2 - (edge_a[1] - p[1]) * dx2) / denominator
        return (p[0] + t * dx1, p[1] + t * dy1)
    out = []
    for p, q in zip(subject, subject[1:] + subject[:1]):
        if left(q):
            if not left(p):
                out.append(cross(p, q))
            out.append(q)
        elif left(p):
            out.append(cross(p, q))
    return out


def _area(polygon):
    return abs(sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(polygon, polygon[1:] + polygon[:1]))) / 2


def box3d_iou(a, b):
    """IoU of two 3-D boxes (center, size, yaw about z): rotated footprints intersected, times the height overlap."""
    footprint = _corners(a[0], a[1], a[2])
    for p, q in zip(_corners(b[0], b[1], b[2]), _corners(b[0], b[1], b[2])[1:] + _corners(b[0], b[1], b[2])[:1]):
        if not footprint:
            break
        footprint = _clip(footprint, p, q)
    base = _area(footprint) if len(footprint) >= 3 else 0.0
    low = max(a[0][2] - a[1][2] / 2, b[0][2] - b[1][2] / 2)
    high = min(a[0][2] + a[1][2] / 2, b[0][2] + b[1][2] / 2)
    inter = base * max(0.0, high - low)
    union = a[1][0] * a[1][1] * a[1][2] + b[1][0] * b[1][1] * b[1][2] - inter
    return inter / union if union > 0 else 0.0


def set_iou(a, b):
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def oks(a, b, sigma=OKS_SIGMA):
    """Object keypoint similarity of two instances' point lists ([x, y], [x, y, v] or None each)."""
    def seen(point):
        return point is not None and (len(point) < 3 or point[2] > 0)

    def area(points):
        shown = [p for p in points if seen(p)]
        if not shown:
            return 0.0
        return (max(p[0] for p in shown) - min(p[0] for p in shown)) * (max(p[1] for p in shown)
                                                                      - min(p[1] for p in shown))
    scale = max(1.0, (area(a) + area(b)) / 2)
    total, count = 0.0, 0
    for p, q in zip(a, b):
        if not seen(p) and not seen(q):
            continue
        count += 1
        if seen(p) and seen(q):
            total += math.exp(-((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) / (2 * scale * sigma ** 2))
    return total / count if count else 1.0


def interval_iou(a, b):
    """IoU of two unions of intervals [(start, end), ...]: the length of their intersection over that of their union."""
    def merged(intervals):
        out = []
        for start, end in sorted(intervals):
            if out and start <= out[-1][1]:
                out[-1][1] = max(out[-1][1], end)
            else:
                out.append([start, end])
        return out
    first, second = merged(a), merged(b)
    inter, i, j = 0.0, 0, 0
    while i < len(first) and j < len(second):
        inter += max(0.0, min(first[i][1], second[j][1]) - max(first[i][0], second[j][0]))
        if first[i][1] < second[j][1]:
            i += 1
        else:
            j += 1
    union = sum(e - s for s, e in first) + sum(e - s for s, e in second) - inter
    return inter / union if union > 0 else 1.0


# ------------------------------------------------------------- matching

def hungarian(scores):
    """The one-to-one assignment of rows to columns maximising the summed score: [(row, column)]."""
    rows, columns = len(scores), len(scores[0]) if scores else 0
    if not rows or not columns:
        return []
    flipped = rows > columns
    if flipped:
        scores = [list(column) for column in zip(*scores)]
        rows, columns = columns, rows
    big = max(max(row) for row in scores)
    cost = [[big - value for value in row] for row in scores]
    # Kuhn-Munkres with potentials (rows <= columns), 1-based.
    u, v, p, way = [0.0] * (rows + 1), [0.0] * (columns + 1), [0] * (columns + 1), [0] * (columns + 1)
    for i in range(1, rows + 1):
        p[0], j0 = i, 0
        minimum, used = [math.inf] * (columns + 1), [False] * (columns + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], math.inf, 0
            for j in range(1, columns + 1):
                if not used[j]:
                    current = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if current < minimum[j]:
                        minimum[j], way[j] = current, j0
                    if minimum[j] < delta:
                        delta, j1 = minimum[j], j
            for j in range(columns + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    pairs = [(p[j] - 1, j - 1) for j in range(1, columns + 1) if p[j]]
    return sorted((c, r) for r, c in pairs) if flipped else sorted(pairs)


def match(first, second, score):
    """Objects (term, payload) of two sides matched one to one within each term: [(i, j, score)] above 0."""
    found = []
    for term in sorted({t for t, _ in first} | {t for t, _ in second}, key=str):
        a = [i for i, (t, _) in enumerate(first) if t == term]
        b = [j for j, (t, _) in enumerate(second) if t == term]
        if not a or not b:
            continue
        table = [[score(first[i][1], second[j][1]) for j in b] for i in a]
        if len(a) <= HUNGARIAN_LIMIT and len(b) <= HUNGARIAN_LIMIT:
            chosen = hungarian(table)
        else:
            ranked = sorted(((table[x][y], x, y) for x in range(len(a)) for y in range(len(b))), reverse=True)
            used_x, used_y, chosen = set(), set(), []
            for value, x, y in ranked:
                if value > 0 and x not in used_x and y not in used_y:
                    used_x.add(x)
                    used_y.add(y)
                    chosen.append((x, y))
        found += [(a[x], b[y], table[x][y]) for x, y in chosen if table[x][y] > 0]
    return found


def _matched(first, second, score):
    """(agreement, figures) of two lists of objects by one-to-one matching."""
    if not first and not second:
        return 1.0, {'matches': 0, 'mean_iou': None, 'f1': 1.0}
    found = match(first, second, score)
    total = sum(value for _, _, value in found)
    good = sum(1 for _, _, value in found if value >= MATCH_IOU)
    f1 = 2 * good / (len(first) + len(second))
    return total / max(len(first), len(second)), {'matches': len(found),
                                                  'mean_iou': total / len(found) if found else None, 'f1': f1}


# ------------------------------------------------------------- the values

def _kept(item, minimum):
    confidence = item.get('confidence') if isinstance(item, dict) else None
    return minimum is None or confidence is None or confidence >= minimum


def filtered(task, entry, minimum):
    """The value of a set's entry after the confidence filter, or None when it holds no annotation."""
    if entry is None or entry.get('value') is None:
        return None
    if minimum is not None and entry.get('confidence') is not None and entry['confidence'] < minimum:
        return None
    value = entry['value']
    if isinstance(value, dict):
        return value if _kept(value, minimum) else None
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return [item for item in value if _kept(item, minimum)]
    return value


def _mask_values(value, load):
    """The pixel values of a mask value, row by row."""
    if 'rle' in value:
        out = array('H')
        for number, count in value['rle']:
            out.extend(array('H', [number]) * count)
        return out
    return payloads.read_png(load(value['file']))[2]


def _point_objects(value, load):
    """A points value as [(term, frozenset of indices)]."""
    if isinstance(value, list):
        return [(item['term'], frozenset(item['indices'])) for item in value]
    _shape, _kind, ids = payloads.read_npy(load(value['file']))
    groups = {}
    for index, identifier in enumerate(ids):
        if identifier:
            groups.setdefault(int(identifier), set()).add(index)
    classes = value.get('classes') or {}
    return [(classes.get(str(identifier), str(identifier)), frozenset(found))
            for identifier, found in sorted(groups.items())]


def _intervals(value):
    by_term = {}
    for item in value:
        by_term.setdefault(item['term'], []).append((item['start'], item['end']))
    return by_term


def _tracks(value):
    return [(item['term'], {frame['frame']: (frame['x'], frame['y'], frame['w'], frame['h'])
                            for frame in item['frames']}, item['track']) for item in value]


def track_iou(a, b):
    frames = set(a) | set(b)
    return sum(box_iou(a[f], b[f]) for f in frames if f in a and f in b) / len(frames) if frames else 0.0


def switches(first, second):
    """Identity switches of first's tracks against second's: the matched track of a frame changing (IoU > 0.5)."""
    count = 0
    for _term, frames, _identifier in first:
        last = None
        for frame in sorted(frames):
            best, chosen = MATCH_IOU, None
            for _t, other, identifier in second:
                if frame in other:
                    value = box_iou(frames[frame], other[frame])
                    if value > best:
                        best, chosen = value, identifier
            if chosen is not None:
                if last is not None and chosen != last:
                    count += 1
                last = chosen
    return count


def fragments(tracks):
    """Gaps in the tracks' frames: a frame number more than one after the one before."""
    return sum(sum(1 for a, b in zip(sorted(f), sorted(f)[1:]) if b - a > 1) for _t, f, _i in tracks)


def compare(document, a, b, load_a=None, load_b=None):
    """(agreement from 0 to 1, figures) of two values of one record under the task document (both not None)."""
    task = document.get('task')
    if task == 'class':
        return (1.0 if a == b else 0.0), {}
    if task == 'tags':
        first, second = set(a), set(b)
        return (len(first & second) / len(first | second) if first | second else 1.0), {}
    if task == 'text':
        same = a == b
        ratio = 1.0 if same else difflib.SequenceMatcher(None, a[:TEXT_COMPARED], b[:TEXT_COMPARED],
                                                         autojunk=False).ratio()
        return ratio, {'exact': same}
    if task == 'ranking':
        tau = kendall_tau(a, b)
        return (tau + 1) / 2, {'tau': tau}
    if task == 'boxes':
        return _matched([(i['term'], (i['x'], i['y'], i['w'], i['h'])) for i in a],
                        [(i['term'], (i['x'], i['y'], i['w'], i['h'])) for i in b], box_iou)
    if task == 'polygons':
        return _matched([(i['term'], [tuple(p) for p in i['points']]) for i in a],
                        [(i['term'], [tuple(p) for p in i['points']]) for i in b], polygon_iou)
    if task == 'box3d':
        return _matched([(i['term'], (i['center'], i['size'], i['yaw'])) for i in a],
                        [(i['term'], (i['center'], i['size'], i['yaw'])) for i in b], box3d_iou)
    if task == 'points':
        return _matched(_point_objects(a, load_a), _point_objects(b, load_b), set_iou)
    if task == 'keypoints':
        sigma = document.get('sigma', OKS_SIGMA)
        agreement, figures = _matched([(i['term'], i['points']) for i in a], [(i['term'], i['points']) for i in b],
                                      lambda p, q: oks(p, q, sigma))
        figures['mean_oks'] = figures.pop('mean_iou')
        return agreement, figures
    if task in ('spans', 'segments', 'timeseries'):
        first, second = _intervals(a), _intervals(b)
        terms = set(first) | set(second)
        if not terms:
            return 1.0, {}
        return sum(interval_iou(first.get(t, []), second.get(t, [])) for t in terms) / len(terms), {}
    if task == 'track':
        first, second = _tracks(a), _tracks(b)
        agreement, figures = _matched([(t, f) for t, f, _ in first], [(t, f) for t, f, _ in second], track_iou)
        figures.update(switches=switches(first, second), fragments=[fragments(first), fragments(second)])
        return agreement, figures
    if task == 'mask':
        return _masks(document, a, b, load_a, load_b)
    if task == 'depth':
        return _depths(a, b, load_a, load_b)
    raise AgreementProblem(f'A {task} task is not compared.')


def _masks(document, a, b, load_a, load_b):
    first, second = _mask_values(a, load_a), _mask_values(b, load_b)
    if len(first) != len(second):
        raise AgreementProblem(f'The two masks cover {len(first):,} and {len(second):,} pixels.')
    classes_a, classes_b = a.get('classes') or {}, b.get('classes') or {}
    joint, count_a, count_b = {}, {}, {}
    for x, y in zip(first, second):
        if x or y:
            joint[(x, y)] = joint.get((x, y), 0) + 1
            count_a[x] = count_a.get(x, 0) + 1
            count_b[y] = count_b.get(y, 0) + 1
    if document.get('mask', 'semantic') == 'instance':
        objects_a = [(classes_a.get(str(v), str(v)), v) for v in sorted(count_a) if v]
        objects_b = [(classes_b.get(str(v), str(v)), v) for v in sorted(count_b) if v]

        def iou(x, y):
            inter = joint.get((x, y), 0)
            return inter / (count_a[x] + count_b[y] - inter) if inter else 0.0
        return _matched(objects_a, objects_b, iou)
    # Semantic: pixels mapped to terms, the IoU of each term either uses.
    inter, union = {}, {}
    for (x, y), n in joint.items():
        tx, ty = classes_a.get(str(x)) if x else None, classes_b.get(str(y)) if y else None
        for term in {tx, ty} - {None}:
            union[term] = union.get(term, 0) + n
        if tx is not None and tx == ty:
            inter[tx] = inter.get(tx, 0) + n
    if not union:
        return 1.0, {'terms': {}}
    ious = {term: inter.get(term, 0) / union[term] for term in sorted(union)}
    return sum(ious.values()) / len(ious), {'terms': ious}


def _depths(a, b, load_a, load_b):
    shape_a, _k, first = payloads.read_npy(load_a(a['file']))
    shape_b, _k, second = payloads.read_npy(load_b(b['file']))
    if shape_a != shape_b:
        raise AgreementProblem(f'The two depth maps have shapes {tuple(shape_a)} and {tuple(shape_b)}.')
    absolute = mean = within = count = 0.0
    for x, y in zip(first, second):
        if x > 0 and y > 0 and math.isfinite(x) and math.isfinite(y):
            count += 1
            absolute += abs(x - y)
            mean += (abs(x) + abs(y)) / 2
            within += max(x / y, y / x) < DEPTH_RATIO
    if not count:
        return 0.0, {'mean_abs': None, 'delta': None, 'pixels': 0}
    return 1 - min(1.0, (absolute / count) / (mean / count)), {'mean_abs': absolute / count, 'delta': within / count,
                                                                'pixels': int(count)}


def kendall_tau(a, b):
    """Kendall's τ of two rankings (best first) over the candidates both rank; 1 when fewer than two are shared."""
    shared = [term for term in a if term in set(b)]
    if len(shared) < 2:
        return 1.0
    position = {term: index for index, term in enumerate(b)}
    concordant = discordant = 0
    for x, y in itertools.combinations(shared, 2):   # x before y in a
        if position[x] < position[y]:
            concordant += 1
        else:
            discordant += 1
    return (concordant - discordant) / (concordant + discordant)


def cohen_kappa(pairs):
    """Cohen's kappa of [(term a, term b)]; 1 when chance agreement is certain; None with no pair."""
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(1 for x, y in pairs if x == y) / n
    first, second = {}, {}
    for x, y in pairs:
        first[x] = first.get(x, 0) + 1
        second[y] = second.get(y, 0) + 1
    expected = sum(first[t] * second.get(t, 0) for t in first) / (n * n)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def fleiss_kappa(rows):
    """Fleiss' kappa of rows of terms (each row the terms every set gave one record); None with no row."""
    if not rows or len(rows[0]) < 2:
        return None
    raters = len(rows[0])
    shares, agreement = {}, 0.0
    for row in rows:
        counts = {}
        for term in row:
            counts[term] = counts.get(term, 0) + 1
            shares[term] = shares.get(term, 0) + 1
        agreement += (sum(c * c for c in counts.values()) - raters) / (raters * (raters - 1))
    observed = agreement / len(rows)
    expected = sum((c / (len(rows) * raters)) ** 2 for c in shares.values())
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


# ------------------------------------------------------------- the sets

def pair_name(a, b):
    return f'{a}|{b}'


def agreement(document, sets, *, min_confidence=None, loaders=None, offset=0, limit=50):
    """The agreement of sets ({name: {record: entry}}, two to eight, in order) under the task document.

    loaders maps a set's name to load(record, file) -> bytes of a sidecar.
    Returns pairs, fleiss, the compared records' count, the disputed list
    (most disputed first, then by record id; offset and limit page it),
    total and problems (records that could not be compared, with why).
    """
    task = document.get('task')
    if task not in MEASURES:
        raise AgreementProblem(f'A {task} task is not compared: it records a decision, not a value.')
    names = list(sets)
    if not 2 <= len(names) <= SETS_LIMIT:
        raise AgreementProblem(f'Agreement needs 2 to {SETS_LIMIT} sets; {len(names)} were given.')
    loaders = loaders or {}
    values = {name: {record: filtered(task, entry, min_confidence) for record, entry in sets[name].items()}
              for name in names}
    records = sorted({record for name in names for record, value in values[name].items() if value is not None},
                     key=lambda record: record.encode('utf-8', 'surrogatepass'))
    pairs = {pair_name(a, b): {'a': a, 'b': b, 'records': 0, 'total': 0.0, 'figures': [], 'labels': []}
             for a, b in itertools.combinations(names, 2)}
    rows, problems = [], []
    for record in records:
        scores, missing = {}, [name for name in names if values[name].get(record) is None]
        for a, b in itertools.combinations(names, 2):
            first, second = values[a].get(record), values[b].get(record)
            if first is None and second is None:
                continue
            key = pair_name(a, b)
            pair = pairs[key]
            pair['records'] += 1
            score = 0.0
            if first is not None and second is not None:
                try:
                    score, figures = compare(document, first, second,
                                             (lambda n, r=record, s=a: loaders[s](r, n)) if a in loaders else None,
                                             (lambda n, r=record, s=b: loaders[s](r, n)) if b in loaders else None)
                    pair['figures'].append(figures)
                    if task == 'class':
                        pair['labels'].append((first, second))
                except (AgreementProblem, payloads.PayloadError, KeyError, OSError) as exc:
                    problems.append({'record': record, 'pair': key, 'problem': str(exc)})
            pair['total'] += score
            scores[key] = score
        if scores:
            rows.append({'record': record, 'disagreement': 1 - sum(scores.values()) / len(scores),
                         'pairs': scores, 'missing': missing})
    rows.sort(key=lambda row: (-row['disagreement'], row['record'].encode('utf-8', 'surrogatepass')))
    answered = []
    for pair in pairs.values():
        shown = {'a': pair['a'], 'b': pair['b'], 'records': pair['records'],
                 'agreement': pair['total'] / pair['records'] if pair['records'] else None}
        shown.update(_figures(task, pair))
        answered.append(shown)
    fleiss = None
    if task == 'class' and len(names) >= 3:
        fleiss = fleiss_kappa([[values[name][record] for name in names] for record in records
                               if all(values[name].get(record) is not None for name in names)])
    return {'type': task, 'measure': MEASURES[task], 'pairs': answered, 'fleiss': fleiss, 'records': len(rows),
            'disputed': rows[offset:offset + limit], 'total': len(rows), 'offset': offset, 'limit': limit,
            'problems': problems[:50]}


def _figures(task, pair):
    """The figures of a pair beyond its agreement, from its records' figures."""
    figures = pair['figures']
    if task == 'class':
        return {'kappa': cohen_kappa(pair['labels'])}
    if task == 'text':
        return {'exact': sum(1 for f in figures if f.get('exact'))}
    if task == 'ranking':
        return {'tau': sum(f['tau'] for f in figures) / len(figures) if figures else None}
    if task in ('boxes', 'polygons', 'box3d', 'points', 'keypoints', 'track') or (figures and 'matches' in figures[0]):
        key = 'mean_oks' if task == 'keypoints' else 'mean_iou'
        matched = [f for f in figures if f.get(key) is not None]
        shown = {'matches': sum(f.get('matches', 0) for f in figures),
                 key: (sum(f[key] * f['matches'] for f in matched) / sum(f['matches'] for f in matched)
                       if matched else None),
                 'f1': sum(f['f1'] for f in figures) / len(figures) if figures else None}
        if task == 'track':
            shown['switches'] = sum(f['switches'] for f in figures)
            shown['fragments'] = [sum(f['fragments'][0] for f in figures), sum(f['fragments'][1] for f in figures)]
        return shown
    if task == 'depth':
        measured = [f for f in figures if f.get('mean_abs') is not None]
        return {'mean_abs': sum(f['mean_abs'] for f in measured) / len(measured) if measured else None,
                'delta': sum(f['delta'] for f in measured) / len(measured) if measured else None}
    return {}
