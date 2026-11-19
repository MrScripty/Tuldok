"""A model's structure: the graph a project's script wrote as model-graph.json, folded, coloured and compared.

Owns sections 1 and 3 of docs/plans/training-and-curation/spec-t2.md above the
file. A run's graph is FILE at the top of its product, else beside one of its
weights files (inside_weights.weight_files, in their order). The file is JSON
written by the project (tuldok_log.graph.export_graph, or by hand); it is
read with the standard library, checked key by key against the format and
its bounds, and refused unsupported when it is not what it says (too-large
past FILE_BYTES). Nothing here imports, runs or unpickles anything of the
project. The checked graph of a file is kept (KEPT of them, least recently
used dropped) while its size, time and inode are unchanged.

model_graph answers the graph folded at a depth of the module tree (with
modules opened or closed by name): an operation inside a closed module is
shown as that module, a node of kind group, and the edges between shown nodes
are merged. model_graph_overlay answers a number per module and per
operation (parameters, output values, operations, or the relative change of
the weights under it, from inside_weights.weights_compare). model_graph_compare
matches the modules of two runs' graphs by path.
"""
import collections
import json
import math
import os
import threading

from . import inside, inside_weights
from .inside_archive import locate
from .store import ProjectError

FILE = 'model-graph.json'
FORMAT = 'tuldok_model_graph_v1'
FILE_BYTES = 32 * 1024 * 1024
NODES = 20_000
EDGES = 100_000
MODULES = 20_000
DEPTH = 64
TENSORS = 100_000
NODE_TENSORS = 64
VALUES = 16
AXES = 16
TEXT = 1024
ATTRIBUTES = 16
LIST = 16
NOTES = 100
LARGE = 200            # operations past which model_graph folds to depth 1 by default
GROUP_TENSORS = 64     # tensors a group lists
KEPT = 8
NODE_KINDS = ('input', 'operation', 'output')
TENSOR_KINDS = ('parameter', 'buffer', 'constant')
OVERLAYS = ('parameters', 'outputs', 'operations', 'change')
GROUP = 'module:'
_lock = threading.Lock()
_kept = collections.OrderedDict()   # (real path, size, time, inode) -> Graph


def _refuse(message, code='unsupported'):
    raise ProjectError(message, code)


def forget():
    with _lock:
        _kept.clear()


# ---------------------------------------------------------------- checking the file

class _Check:
    """Checks the parts of a decoded file, naming where a problem is."""

    @staticmethod
    def text(value, where, *, empty=True):
        if not isinstance(value, str) or len(value) > TEXT or (not empty and not value):
            _refuse(f'{FILE}: {where} must be a string of {"1" if not empty else "0"} to {TEXT} characters.')
        return value

    @staticmethod
    def optional_text(value, where):
        return None if value is None else _Check.text(value, where)

    @staticmethod
    def items(value, where, most):
        if not isinstance(value, list):
            _refuse(f'{FILE}: {where} must be a list.')
        if len(value) > most:
            _refuse(f'{FILE}: {where} holds {len(value)} items; at most {most} are read.')
        return value

    @staticmethod
    def mapping(value, where, keys=()):
        if not isinstance(value, dict):
            _refuse(f'{FILE}: {where} must be an object.')
        missing = [key for key in keys if key not in value]
        if missing:
            _refuse(f'{FILE}: {where} has no {", ".join(missing)}.')
        return value

    @staticmethod
    def count(value, where):
        if type(value) is not int or value < 0:
            _refuse(f'{FILE}: {where} must be a whole number of at least 0.')
        return value

    @classmethod
    def shape(cls, value, where):
        cls.items(value, where, AXES)
        for size in value:
            if not ((type(size) is int and size >= 0) or (isinstance(size, str) and 0 < len(size) <= 64)):
                _refuse(f'{FILE}: {where} must hold sizes (whole numbers of at least 0, or names of a symbol).')
        return list(value)

    @classmethod
    def value(cls, value, where, named=False):
        cls.mapping(value, where, ('shape', 'dtype') + (('name',) if named else ()))
        out = {'shape': cls.shape(value['shape'], where + '.shape'), 'dtype': cls.text(value['dtype'], where + '.dtype')}
        if named:
            out = {'name': cls.text(value['name'], where + '.name'), **out}
        return out

    @classmethod
    def values(cls, value, where, named=False):
        return [cls.value(item, f'{where}[{i}]', named) for i, item in enumerate(cls.items(value, where, VALUES))]

    @classmethod
    def attribute(cls, value, where, nested=False):
        if value is None or isinstance(value, (bool, int, str)):
            if isinstance(value, str):
                cls.text(value, where)
            return value
        if isinstance(value, float):
            return value
        if isinstance(value, list) and not nested:
            return [cls.attribute(item, where, True) for item in cls.items(value, where, LIST)]
        _refuse(f'{FILE}: {where} must be a number, a boolean, a string, null or a short list of those.')


def _no_constant(name):
    raise ValueError(f'{name} is not JSON')


class Graph:
    """A checked model-graph.json: its fields, its nodes and edges, and its module tree, flat and as given."""

    def __init__(self, document):
        c = _Check
        c.mapping(document, 'the file', ('format', 'complete', 'nodes', 'edges', 'modules', 'tensors'))
        if document['format'] != FORMAT:
            _refuse(f'{FILE}: format must be {FORMAT}.')
        if not isinstance(document['complete'], bool):
            _refuse(f'{FILE}: complete must be true or false.')
        self.complete = document['complete']
        self.reason = c.optional_text(document.get('reason'), 'reason')
        self.method = c.optional_text(document.get('method'), 'method')
        self.torch = c.optional_text(document.get('torch'), 'torch')
        self.model = c.optional_text(document.get('model'), 'model')
        self.inputs = c.values(document.get('inputs', []), 'inputs', named=True)
        self.notes = [c.text(note, f'notes[{i}]') for i, note in enumerate(c.items(document.get('notes', []),
                                                                                     'notes', NOTES))]
        self._tensors(document['tensors'])
        self._modules(document['modules'])
        self._nodes(document['nodes'] if self.complete else [])
        self._edges(document['edges'] if self.complete else [])
        self.operations = sum(1 for node in self.nodes if node['kind'] == 'operation')

    def _tensors(self, value):
        c = _Check
        c.mapping(value, 'tensors')
        if len(value) > TENSORS:
            _refuse(f'{FILE}: tensors holds {len(value)} tensors; at most {TENSORS} are read.')
        self.tensors = {}
        for name, item in value.items():
            where = f'tensors[{name[:80]!r}]'
            c.text(name, where, empty=False)
            c.mapping(item, where, ('shape', 'dtype'))
            kind = item.get('kind', 'parameter')
            if kind not in TENSOR_KINDS:
                _refuse(f'{FILE}: {where}.kind must be one of {", ".join(TENSOR_KINDS)}.')
            self.tensors[name] = {'shape': c.shape(item['shape'], where + '.shape'),
                                  'dtype': c.text(item['dtype'], where + '.dtype'), 'kind': kind}

    def _modules(self, root):
        """The tree, checked without recursion: self.tree (as answered) and self.modules {path: info}, in the tree's
        depth-first order."""
        c = _Check
        self.modules = collections.OrderedDict()
        c.mapping(root, 'modules', ('path', 'class', 'parameters', 'children'))
        if root['path'] != '':
            _refuse(f'{FILE}: the module tree must start at the model itself, path "".')
        self.tree = {}
        stack = [(root, None, 0, self.tree)]
        while stack:
            item, parent, depth, out = stack.pop()
            where = f'modules {str(item.get("path", "?"))[:80]!r}' if isinstance(item, dict) else 'modules'
            c.mapping(item, where, ('path', 'class', 'parameters', 'children'))
            path = c.text(item['path'], where + '.path')
            if parent is not None and (not path or (parent and not path.startswith(parent + '.'))):
                _refuse(f'{FILE}: {where}: a module\'s path must extend its parent\'s ({parent!r}).')
            if path in self.modules:
                _refuse(f'{FILE}: the module {path[:80]!r} is listed twice.')
            if len(self.modules) >= MODULES:
                _refuse(f'{FILE}: the module tree holds more than {MODULES} modules.')
            children = c.items(item['children'], where + '.children', MODULES)
            if children and depth >= DEPTH:
                _refuse(f'{FILE}: the module tree is deeper than {DEPTH}.')
            kids = [{} for _ in children]
            out.update({'path': path, 'class': c.text(item['class'], where + '.class'),
                        'parameters': c.count(item['parameters'], where + '.parameters'), 'children': kids})
            self.modules[path] = {'class': out['class'], 'parameters': out['parameters'], 'parent': parent,
                                  'depth': 0 if not path else path.count('.') + 1, 'children': []}
            if parent is not None:
                self.modules[parent]['children'].append(path)
            for child, kid in reversed(list(zip(children, kids))):
                stack.append((child, path, depth + 1, kid))

    def _nodes(self, value):
        c = _Check
        self.nodes, self.index = [], {}
        for i, item in enumerate(c.items(value, 'nodes', NODES)):
            where = f'nodes[{i}]'
            c.mapping(item, where, ('id', 'kind', 'operation', 'module', 'tensors', 'inputs', 'outputs'))
            identifier = c.text(item['id'], where + '.id', empty=False)
            if identifier.startswith(GROUP):
                _refuse(f'{FILE}: {where}.id may not begin "{GROUP}".')
            if identifier in self.index:
                _refuse(f'{FILE}: the node id {identifier[:80]!r} is used twice.')
            if item['kind'] not in NODE_KINDS:
                _refuse(f'{FILE}: {where}.kind must be one of {", ".join(NODE_KINDS)}.')
            module = c.text(item['module'], where + '.module')
            while module and module not in self.modules:
                module = module.rpartition('.')[0]   # a module the tree does not list: its nearest listed parent
            tensors = [c.text(name, f'{where}.tensors', empty=False)
                       for name in c.items(item['tensors'], where + '.tensors', NODE_TENSORS)]
            attributes = c.mapping(item.get('attributes', {}), where + '.attributes')
            if len(attributes) > ATTRIBUTES:
                _refuse(f'{FILE}: {where}.attributes holds more than {ATTRIBUTES} attributes.')
            self.index[identifier] = len(self.nodes)
            self.nodes.append({
                'id': identifier, 'kind': item['kind'], 'operation': c.text(item['operation'], where + '.operation'),
                'module': module, 'tensors': list(dict.fromkeys(tensors)),
                'inputs': c.values(item['inputs'], where + '.inputs'),
                'outputs': c.values(item['outputs'], where + '.outputs'),
                'attributes': {c.text(key, where + '.attributes', empty=False)[:200]:
                               c.attribute(entry, f'{where}.attributes') for key, entry in attributes.items()}})

    def _edges(self, value):
        c = _Check
        self.edges = []
        for i, item in enumerate(c.items(value, 'edges', EDGES)):
            where = f'edges[{i}]'
            c.mapping(item, where, ('from', 'to'))
            ends = []
            for key in ('from', 'to'):
                if not isinstance(item[key], str) or item[key] not in self.index:
                    _refuse(f'{FILE}: {where}.{key} names no node.')
                ends.append(self.index[item[key]])
            self.edges.append((ends[0], ends[1], c.count(item.get('input', 0), where + '.input')))


def _read(place):
    if (place.size or 0) > FILE_BYTES:
        _refuse(f'{place.address} is {place.size} bytes; at most {FILE_BYTES} are read.', 'too-large')
    raw = bytes(place.head(place.size or 0))
    try:
        document = json.loads(raw.decode('utf-8'), parse_constant=_no_constant)
    except (ValueError, RecursionError):
        _refuse(f'{place.address} is not JSON.')
    return Graph(document)


def _graph_place(product):
    """The Place of a run's graph file: at the top of the product, else beside one of its weights files."""
    candidates = [FILE]
    for address, _ in inside_weights.weight_files(product):
        folder = address.rpartition('/')[0]
        candidates.append(f'{folder}/{FILE}' if folder else FILE)
    for address in dict.fromkeys(candidates):
        try:
            place = locate(product.root, address)
        except ProjectError:
            continue
        if place.kind == 'file':
            return place
    raise ProjectError(f'Run {product.run_id} has no {FILE}.', 'not-found')


def graph_of(product):
    """(the Place, the checked Graph) of a run's graph file, kept while the file is unchanged."""
    place = _graph_place(product)
    info = os.stat(place.path)
    key = (place.path, info.st_size, info.st_mtime_ns, info.st_ino)
    with _lock:
        if key in _kept:
            _kept.move_to_end(key)
            return place, _kept[key]
    graph = _read(place)
    with _lock:
        _kept[key] = graph
        while len(_kept) > KEPT:
            _kept.popitem(last=False)
    return place, graph


# ---------------------------------------------------------------- folding

def _label(operation):
    """A short name of an operation: aten.conv2d.default -> conv2d; torch.nn.modules.conv.Conv2d -> Conv2d."""
    parts = operation.split('.')
    if len(parts) >= 3 and parts[0] in ('aten', 'prims', 'quantized'):
        return parts[1]
    return parts[-1] or operation


def _size(shape):
    total = 1
    for size in shape:
        if not isinstance(size, int):
            return None
        total *= size
    return total


def _node_parameters(graph, tensors):
    return sum(_size(graph.tensors[name]['shape']) or 0 for name in tensors
               if name in graph.tensors and graph.tensors[name]['kind'] == 'parameter')


class _Folding:
    def __init__(self, graph, depth, opened, closed):
        self.graph, self.depth, self.opened, self.closed = graph, depth, set(opened), set(closed)
        self.groups = {}

    def is_open(self, path):
        if not path:
            return True
        if path in self.opened:
            return True
        return self.graph.modules[path]['depth'] <= self.depth and path not in self.closed

    def group(self, module):
        """The shallowest closed module on module's path, or None when every one is open."""
        if module in self.groups:
            return self.groups[module]
        found, path = None, ''
        for part in module.split('.') if module else []:
            path = f'{path}.{part}' if path else part
            if path in self.graph.modules and not self.is_open(path):
                found = path
                break
        self.groups[module] = found
        return found

    def open_in_effect(self):
        return [path for path in self.graph.modules if path and self.group(path) is None]


def fold(graph, depth=None, opened=(), closed=()):
    """The shown nodes and merged edges of graph folded at depth with the modules opened and closed by name."""
    if depth is None:
        depth = 1 if graph.operations > LARGE else DEPTH
    folding = _Folding(graph, depth, opened, closed)
    shown, order, place = {}, [], []
    for position, node in enumerate(graph.nodes):
        group = folding.group(node['module']) if node['kind'] == 'operation' else None
        if group is None:
            key = node['id']
            shown[key] = {'id': key, 'kind': node['kind'], 'label': _label(node['operation']) if node['kind'] ==
                          'operation' else node['id'], 'module': node['module'],
                          'class': graph.modules.get(node['module'], {}).get('class'),
                          'operation': node['operation'], 'tensors': node['tensors'],
                          'tensor_count': len(node['tensors']),
                          'parameters': _node_parameters(graph, node['tensors']), 'inputs': node['inputs'],
                          'outputs': node['outputs'], 'attributes': node['attributes'], 'operations': 1,
                          'first': position}
            order.append(key)
        else:
            key = GROUP + group
            entry = shown.get(key)
            if entry is None:
                module = graph.modules[group]
                entry = shown[key] = {'id': key, 'kind': 'group', 'label': group, 'module': group,
                                      'class': module['class'], 'operation': None, 'tensors': [],
                                      'tensor_count': 0, 'parameters': module['parameters'], 'inputs': [],
                                      'outputs': [], 'attributes': {}, 'operations': 0, 'first': position,
                                      '_tensors': {}}
                order.append(key)
            entry['operations'] += 1
            for name in node['tensors']:
                entry['_tensors'][name] = None
        place.append(key)
    edges = collections.OrderedDict()
    for source, target, _ in graph.edges:
        a, b = place[source], place[target]
        if a == b:
            continue
        value = graph.nodes[source]['outputs'][:1]
        edge = edges.get((a, b))
        if edge is None:
            edge = edges[(a, b)] = {'from': a, 'to': b, 'count': 0,
                                    'shape': value[0]['shape'] if value else None,
                                    'dtype': value[0]['dtype'] if value else None}
        edge['count'] += 1
        if shown[b]['kind'] == 'group' and value and len(shown[b]['inputs']) < VALUES:
            shown[b]['inputs'].append(value[0])
        if shown[a]['kind'] == 'group' and value and len(shown[a]['outputs']) < VALUES and edge['count'] == 1:
            shown[a]['outputs'].append(value[0])
    for entry in shown.values():
        held = entry.pop('_tensors', None)
        if held is not None:
            names = list(held)
            entry['tensors'], entry['tensor_count'] = names[:GROUP_TENSORS], len(names)
    return {'depth': depth, 'open': folding.open_in_effect(), 'nodes': [shown[key] for key in order],
            'edges': list(edges.values())}


def _head(place, graph):
    return {'path': place.address, 'format': FORMAT, 'complete': graph.complete, 'reason': graph.reason,
            'method': graph.method, 'torch': graph.torch, 'model': graph.model, 'inputs': graph.inputs,
            'notes': graph.notes,
            'counts': {'nodes': len(graph.nodes), 'edges': len(graph.edges), 'operations': graph.operations,
                       'modules': len(graph.modules), 'tensors': len(graph.tensors)}}


@inside.reading
def model_graph(product, *, depth=None, opened=(), closed=()):
    place, graph = graph_of(product)
    return {**_head(place, graph), 'modules': graph.tree, 'tensors': graph.tensors,
            **fold(graph, depth, opened, closed)}


# ---------------------------------------------------------------- overlays

def _prefixes(name):
    """The module paths a dotted tensor name (or a module path) lies under, the model itself first."""
    out, path = [''], ''
    parts = name.split('.')
    for part in parts[:-1]:
        path = f'{path}.{part}' if path else part
        out.append(path)
    return out


def _module_prefixes(module):
    return _prefixes(module + '.x') if module else ['']


def _finite(values):
    return [value for value in values if value is not None and math.isfinite(value)]


def _counts(graph, kind):
    modules = {path: 0 for path in graph.modules}
    nodes = {}
    for node in graph.nodes:
        if node['kind'] != 'operation':
            continue
        if kind == 'outputs':
            sizes = [_size(value['shape']) for value in node['outputs']]
            value = None if any(size is None for size in sizes) else sum(sizes)
        else:
            value = 1
        nodes[node['id']] = value
        for path in _module_prefixes(node['module']):
            if path in modules:
                modules[path] = None if modules[path] is None or value is None else modules[path] + value
    return modules, nodes


def _relative(sums):
    difference, other, bad = sums
    if bad or not other:
        return None
    return math.sqrt(difference) / math.sqrt(other)


def _changes(graph, compared):
    """{module: relative change}, {node: relative change} from the rows of a weights_compare."""
    rows = {row['array']: row for row in compared['tensors']}
    modules = {path: [0.0, 0.0, False, 0] for path in graph.modules}

    def add(sums, row):
        if row['difference_norm'] is None or row['other_norm'] is None:
            sums[2] = True
        else:
            sums[0] += row['difference_norm'] ** 2
            sums[1] += row['other_norm'] ** 2
        sums[3] += 1
    for name, row in rows.items():
        for path in _prefixes(name):
            if path in modules:
                add(modules[path], row)
    nodes = {}
    for node in graph.nodes:
        if node['kind'] != 'operation':
            continue
        sums = [0.0, 0.0, False, 0]
        for name in node['tensors']:
            if name in rows:
                add(sums, rows[name])
        nodes[node['id']] = _relative(sums[:3]) if sums[3] else None
    return {path: (_relative(sums[:3]) if sums[3] else None) for path, sums in modules.items()}, nodes


def _readable_weights(product, path=None):
    """The address of a readable weights file of a product: path when given, else the first readable one."""
    if path is not None:
        return path
    for address, output in inside_weights.weight_files(product):
        if inside_weights._weights_file(product, address, output)['readable']:
            return address
    raise ProjectError(f'Run {product.run_id} has no weights file Tuldok reads.', 'not-found')


@inside.reading
def model_graph_overlay(product, *, kind, against=None, other=None, path=None, other_path=None):
    _, graph = graph_of(product)
    extra = {}
    if kind == 'parameters':
        modules = {name: module['parameters'] for name, module in graph.modules.items()}
        nodes = {node['id']: _node_parameters(graph, node['tensors']) for node in graph.nodes
                 if node['kind'] == 'operation'}
        unit = 'parameters'
    elif kind in ('outputs', 'operations'):
        modules, nodes = _counts(graph, kind)
        unit = 'values' if kind == 'outputs' else 'operations'
    elif kind == 'change':
        here = _readable_weights(product, path)
        if against == 'start':
            other, other_path = product, other_path or inside_weights._starts_from(product, here)
            if other_path is None:
                raise ProjectError(f'{here} has no initial- file beside it to compare with.', 'not-found')
        elif against == 'run':
            if other is None:
                raise ProjectError('Name the other run to compare with (other_run).', 'invalid')
            other_path = _readable_weights(other, other_path)
        else:
            raise ProjectError('against must be start or run for the change overlay.', 'invalid')
        compared = inside_weights.weights_compare(product, path=here, other=other, other_path=other_path)
        modules, nodes = _changes(graph, compared)
        unit = 'relative change'
        extra = {'against': {'kind': against, 'run': product.run_id, 'path': here, 'other_run': other.run_id,
                             'other_path': other_path}}
    else:
        raise ProjectError(f'kind must be one of {", ".join(OVERLAYS)}.', 'invalid')
    finite = _finite(list(modules.values()) + list(nodes.values()))
    return {'kind': kind, 'unit': unit, 'modules': modules, 'nodes': nodes,
            'low': min(finite) if finite else None, 'high': max(finite) if finite else None, **extra}


# ---------------------------------------------------------------- comparing

def _own_tensors(graph):
    """{module path: {tensor name: shape}} of the tensors directly in each module."""
    owned = collections.defaultdict(dict)
    for name, tensor in graph.tensors.items():
        module = name.rpartition('.')[0]
        owned[module][name] = tensor['shape']
    return owned


@inside.reading
def model_graph_compare(product, *, other):
    _, here = graph_of(product)
    _, there = graph_of(other)
    mine, theirs = _own_tensors(here), _own_tensors(there)
    rows = []
    for path in list(here.modules) + [path for path in there.modules if path not in here.modules]:
        a, b = here.modules.get(path), there.modules.get(path)
        row = {'path': path, 'class': a['class'] if a else None, 'other_class': b['class'] if b else None,
               'parameters': a['parameters'] if a else None, 'other_parameters': b['parameters'] if b else None,
               'reshaped': [], 'only_here': [], 'only_there': []}
        if a is None:
            row['status'] = 'missing'
        elif b is None:
            row['status'] = 'added'
        else:
            ours, others = mine.get(path, {}), theirs.get(path, {})
            row['reshaped'] = [{'name': name, 'shape': shape, 'other_shape': others[name]}
                               for name, shape in ours.items() if name in others and others[name] != shape]
            row['only_here'] = [name for name in ours if name not in others]
            row['only_there'] = [name for name in others if name not in ours]
            row['status'] = 'changed' if (a['class'] != b['class'] or row['reshaped'] or row['only_here']
                                          or row['only_there']) else 'same'
        rows.append(row)
    counts = collections.Counter(row['status'] for row in rows)
    return {'modules': rows, 'counts': {status: counts.get(status, 0)
                                        for status in ('same', 'changed', 'added', 'missing')}}
