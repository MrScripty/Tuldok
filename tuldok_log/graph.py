"""Write a PyTorch model's structure as model-graph.json, the file Tuldok draws (docs/plans/training-and-curation/spec-t2.md).

export_graph(model, example_inputs, path) records the model's operations from
its inputs to its outputs, with the module each ran in, the parameter and
buffer tensors each reads (by the names of the model's state_dict, which are
the names its weights file uses), the shapes and types of what each takes and
gives, and the tree of the model's modules. It tries torch.export.export
first, then torch.fx.symbolic_trace with one forward pass for the shapes, and
when both fail (a forward that branches on data values, say) writes the
module tree alone with complete false and the reason. It imports PyTorch only
inside export_graph, writes JSON only (never a pickle), and replaces the file
in one rename, so a reader never sees half of it. The bounds are section 1 of
the spec; a graph past them is written as its module tree with the reason.
"""
import json
import math
import os
import re
import uuid

FORMAT = 'tuldok_model_graph_v1'
FILE = 'model-graph.json'
NODES = 20_000
EDGES = 100_000
MODULES = 20_000
DEPTH = 64
TENSORS = 100_000
NODE_TENSORS = 64
VALUES = 16          # inputs or outputs of a node
AXES = 16
TEXT = 1024
ATTRIBUTES = 16
LIST = 16
REASON = 400


def _text(value, most=TEXT):
    value = str(value)
    return value if len(value) <= most else value[:most - 1] + '…'


def _first_line(error):
    lines = str(error).strip().splitlines()
    return _text(f'{type(error).__name__}: {lines[0] if lines else ""}'.rstrip(': '), REASON)


def _class(module):
    kind = type(module)
    return _text(f'{kind.__module__}.{kind.__qualname__}')


def _dtype(dtype):
    return _text(str(dtype).replace('torch.', ''), 64)


def _shape(shape):
    out = []
    for size in list(shape)[:AXES]:
        try:
            out.append(int(size))
        except (TypeError, ValueError):
            out.append(_text(size, 64))   # a symbolic size
    return out


def _plain(value, depth=0):
    """value as a JSON-plain attribute, or a marker object _SKIP when it is not one."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, str):
        return _text(value, 200)
    if isinstance(value, (list, tuple)) and depth == 0:
        items = [_plain(item, 1) for item in value[:LIST]]
        return _SKIP if any(item is _SKIP for item in items) else items
    if type(value).__module__.startswith('torch') and type(value).__name__ in ('dtype', 'device', 'layout',
                                                                               'memory_format'):
        return _text(str(value).replace('torch.', ''), 64)
    return _SKIP


_SKIP = object()


# ------------------------------------------------------------------ the module tree

def module_tree(model):
    """The tree of model's modules: {path, class, parameters, children}, at most MODULES modules, DEPTH deep."""
    count = [0]

    def node(module, path, depth):
        count[0] += 1
        children = []
        if depth < DEPTH:
            for name, child in module.named_children():
                if count[0] >= MODULES:
                    break
                children.append(node(child, f'{path}.{name}' if path else name, depth + 1))
        return {'path': _text(path), 'class': _class(module),
                'parameters': sum(p.numel() for p in module.parameters()), 'children': children}
    return node(model, '', 0), count[0] >= MODULES


def _tensors(model):
    found = {}
    parameters = {name for name, _ in model.named_parameters(remove_duplicate=False)}
    for name, tensor in model.state_dict(keep_vars=True).items():
        if len(found) >= TENSORS:
            break
        found[_text(name)] = {'shape': _shape(tensor.shape), 'dtype': _dtype(tensor.dtype),
                              'kind': 'parameter' if name in parameters else 'buffer'}
    for name, tensor in model.named_buffers():
        if name not in found and len(found) < TENSORS:   # a buffer that is not persistent
            found[_text(name)] = {'shape': _shape(tensor.shape), 'dtype': _dtype(tensor.dtype), 'kind': 'buffer'}
    return found


# ------------------------------------------------------------------ values

def _values(value):
    """[{shape, dtype}] of the tensors in value (a tensor, a fake tensor, tensor metadata or a sequence of them)."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)) and not hasattr(value, 'shape'):
        out = []
        for item in value:
            out.extend(_values(item))
        return out[:VALUES]
    shape, dtype = getattr(value, 'shape', None), getattr(value, 'dtype', None)
    if shape is None or dtype is None:
        return []
    return [{'shape': _shape(shape), 'dtype': _dtype(dtype)}]


_STACK_PATH = re.compile(r"\._modules\[['\"]([^'\"]+)['\"]\]|\[['\"]([^'\"]+)['\"]\]|\[(\d+)\]")


def _module_path(raw, known):
    """A module path of nn_module_stack in the dotted form of named_modules ('' for the model)."""
    text = str(raw)
    for prefix in ("L['self'].", "L['self']", 'L__self__.', 'L__self__', 'self.', 'self'):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    text = _STACK_PATH.sub(lambda m: '.' + (m.group(1) or m.group(2) or m.group(3)), text).strip('.')
    while text and text not in known:
        text = text.rpartition('.')[0]
    return text


def _operation_name(target):
    if isinstance(target, str):
        return _text(target, 200)
    name = getattr(target, '__name__', None)
    if type(target).__name__ in ('OpOverload', 'OpOverloadPacket'):
        return _text(str(target), 200)
    module = getattr(target, '__module__', None)
    return _text(f'{module}.{name}' if module and name else str(target), 200)


def _attributes(node, Node):
    """Up to ATTRIBUTES of a call's arguments that are not graph values, by name where the schema gives one."""
    found = {}
    names = []
    schema = getattr(node.target, '_schema', None)
    if schema is not None:
        names = [argument.name for argument in schema.arguments]
    for position, value in enumerate(node.args):
        if _holds_node(value, Node):
            continue
        plain = _plain(value)
        if plain is not _SKIP:
            found[names[position] if position < len(names) else f'arg{position}'] = plain
    for key, value in node.kwargs.items():
        if _holds_node(value, Node):
            continue
        plain = _plain(value)
        if plain is not _SKIP:
            found[_text(key, 64)] = plain
    return dict(list(found.items())[:ATTRIBUTES])


def _holds_node(value, Node):
    if isinstance(value, Node):
        return True
    if isinstance(value, (list, tuple)):
        return any(_holds_node(item, Node) for item in value)
    if isinstance(value, dict):
        return any(_holds_node(item, Node) for item in value.values())
    return False


def _node_arguments(node, Node):
    """The graph values a node reads, in the order of its arguments."""
    out = []

    def walk(value):
        if isinstance(value, Node):
            out.append(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
    walk(node.args)
    walk(node.kwargs)
    return out


class _Graph:
    """The nodes and edges being written, with the names of the values that are tensors of the model."""

    def __init__(self, Node):
        self.Node = Node
        self.nodes, self.edges, self.ids, self.notes = [], [], {}, []
        self.tensor_of = {}    # graph value name -> state_dict name

    def add(self, fx_node, kind, operation, module, tensors, outputs, attributes):
        if len(tensors) > NODE_TENSORS:
            self.notes.append(f'{fx_node.name} reads {len(tensors)} tensors; the first {NODE_TENSORS} are listed.')
        entry = {'id': _text(fx_node.name, 200), 'kind': kind, 'operation': operation, 'module': module,
                 'tensors': tensors[:NODE_TENSORS], 'inputs': [], 'outputs': outputs[:VALUES],
                 'attributes': attributes}
        self.ids[fx_node] = entry
        self.nodes.append(entry)
        return entry

    def connect(self, fx_node, entry, values):
        position = 0
        for value in values:
            source = self.ids.get(value)
            if source is None:
                continue
            self.edges.append({'from': source['id'], 'to': entry['id'], 'input': position})
            if len(entry['inputs']) < VALUES:
                entry['inputs'].extend(source['outputs'][:1])
            position += 1


def _from_export(model, example_inputs, torch, known):
    exported = torch.export.export(model, tuple(example_inputs), strict=False)
    graph_module = exported.graph_module
    Node = torch.fx.Node
    signature = exported.graph_signature
    kinds = {}
    for spec in signature.input_specs:
        name = getattr(spec.arg, 'name', None)
        kinds[name] = (spec.kind.name, spec.target)
    user_outputs = {getattr(spec.arg, 'name', None) for spec in signature.output_specs
                    if spec.kind.name == 'USER_OUTPUT'}
    graph = _Graph(Node)
    for node in graph_module.graph.nodes:
        if node.op == 'placeholder':
            kind, target = kinds.get(node.name, ('USER_INPUT', None))
            if kind in ('PARAMETER', 'BUFFER', 'CONSTANT_TENSOR'):
                if target is not None:
                    graph.tensor_of[node] = _text(target)
                continue
            graph.add(node, 'input', 'input', '', [], _values(node.meta.get('val')), {})
        elif node.op == 'get_attr':
            graph.tensor_of[node] = _text(node.target)
        elif node.op == 'call_function':
            stack = node.meta.get('nn_module_stack') or {}
            module = _module_path(list(stack.values())[-1][0], known) if stack else ''
            values = _node_arguments(node, Node)
            tensors = [graph.tensor_of[value] for value in values if value in graph.tensor_of]
            entry = graph.add(node, 'operation', _operation_name(node.target), module,
                              list(dict.fromkeys(tensors)), _values(node.meta.get('val')),
                              _attributes(node, Node))
            graph.connect(node, entry, [value for value in values if value not in graph.tensor_of])
        elif node.op == 'output':
            values = [value for value in _node_arguments(node, Node)
                      if value not in graph.tensor_of and (not user_outputs or value.name in user_outputs)]
            entry = graph.add(node, 'output', 'output', '', [],
                              [item for value in values if value in graph.ids for item in graph.ids[value]['outputs'][:1]],
                              {})
            graph.connect(node, entry, values)
        if len(graph.nodes) > NODES:
            raise _TooLarge(f'The exported graph has more than {NODES} nodes; the module tree alone is written.')
    return graph


def _from_fx(model, example_inputs, torch, known):
    from torch.fx.passes.shape_prop import ShapeProp
    traced = torch.fx.symbolic_trace(model)
    ShapeProp(traced).propagate(*example_inputs)
    Node = torch.fx.Node
    graph = _Graph(Node)
    owned = {path: [f'{path}.{name}' for name, _ in module.named_parameters()]
             + [f'{path}.{name}' for name, _ in module.named_buffers()]
             for path, module in traced.named_modules() if path}
    for node in traced.graph.nodes:
        shapes = _values(node.meta.get('tensor_meta'))
        if node.op == 'placeholder':
            graph.add(node, 'input', 'input', '', [], shapes, {})
        elif node.op == 'get_attr':
            graph.tensor_of[node] = _text(node.target)
        elif node.op in ('call_module', 'call_function', 'call_method'):
            values = _node_arguments(node, Node)
            tensors = [graph.tensor_of[value] for value in values if value in graph.tensor_of]
            if node.op == 'call_module':
                module = _module_path(node.target, known)
                operation = _class(traced.get_submodule(node.target))
                tensors = owned.get(node.target, []) + tensors
                sub = traced.get_submodule(node.target)
                attributes = {'repr': _text(sub.extra_repr(), 200)} if sub.extra_repr() else {}
            else:
                module = ''
                operation = ('Tensor.' + node.target) if node.op == 'call_method' else _operation_name(node.target)
                attributes = _attributes(node, Node)
            entry = graph.add(node, 'operation', operation, module, list(dict.fromkeys(tensors)), shapes,
                              attributes)
            graph.connect(node, entry, [value for value in values if value not in graph.tensor_of])
        elif node.op == 'output':
            values = [value for value in _node_arguments(node, Node) if value not in graph.tensor_of]
            entry = graph.add(node, 'output', 'output', '', [],
                              [item for value in values if value in graph.ids for item in graph.ids[value]['outputs'][:1]],
                              {})
            graph.connect(node, entry, values)
        if len(graph.nodes) > NODES:
            raise _TooLarge(f'The traced graph has more than {NODES} nodes; the module tree alone is written.')
    return graph


class _TooLarge(Exception):
    pass


# ------------------------------------------------------------------ writing

def _destination(path):
    path = os.fspath(path)
    return os.path.join(path, FILE) if os.path.isdir(path) else path


def _write(document, path):
    """document as JSON at path, through a file beside it renamed into place (made with the process's umask)."""
    folder, name = os.path.split(os.path.abspath(path))
    temporary = os.path.join(folder, f'.{name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp')
    try:
        with open(temporary, 'x', encoding='utf-8') as out:
            json.dump(document, out, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
            out.write('\n')
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def export_graph(model, example_inputs, path):
    """Write model's structure, traced on example_inputs (a tensor or a tuple of them), as model-graph.json at
    path (a file, or a directory to write model-graph.json in); return what was written."""
    import torch
    if isinstance(example_inputs, torch.Tensor):
        example_inputs = (example_inputs,)
    example_inputs = tuple(example_inputs)
    tree, cut = module_tree(model)
    known = {path_ for path_, _ in model.named_modules()}
    notes = [f'The model has more than {MODULES} modules; the first are listed.'] if cut else []
    inputs = [{'name': f'input{position}', **value} for position, item in enumerate(example_inputs)
              for value in _values(item)[:1]][:VALUES]
    graph, method, reasons = None, 'module-tree', []
    for name, build in (('torch.export', _from_export), ('torch.fx', _from_fx)):
        try:
            graph = build(model, example_inputs, torch, known)
            method = name
            break
        except _TooLarge as error:
            reasons.append(str(error))
            break
        except Exception as error:   # a model export or tracing cannot follow; the next way is tried
            reasons.append(f'{name} failed ({_first_line(error)})')
    if graph is not None and len(graph.edges) > EDGES:
        reasons.append(f'The graph has more than {EDGES} edges; the module tree alone is written.')
        graph, method = None, 'module-tree'
    if graph is not None and reasons:
        notes.append('Exported by torch.fx after ' + '; '.join(reasons) + '.')
    if graph is not None:
        inputs = [{'name': node['id'], **node['outputs'][0]} for node in graph.nodes
                  if node['kind'] == 'input' and node['outputs']][:VALUES] or inputs
        notes.extend(graph.notes)
    document = {
        'format': FORMAT, 'complete': graph is not None,
        'reason': None if graph is not None else _text('; '.join(reasons) + '.', TEXT),
        'method': method, 'torch': _text(torch.__version__, 64), 'model': _class(model), 'inputs': inputs,
        'tensors': _tensors(model), 'nodes': graph.nodes if graph is not None else [],
        'edges': graph.edges if graph is not None else [], 'modules': tree,
        'notes': [_text(note) for note in notes[:100]],
    }
    _write(document, _destination(path))
    return document
