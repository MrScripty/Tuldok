"""Dispatch admission only; Runs retains authorization, execution and drainage.

Memory reservations are conservative operator budgets, not OS memory limits.
Queued jobs never consume a reservation; unknown custody fences further dispatch.
"""
from dataclasses import dataclass, field
import os
from pathlib import Path

MIB = 1024 * 1024
MAX_ATTEMPTS = 8


def usable_cores():
    available = tuple(sorted(os.sched_getaffinity(0)))
    return available[2:] if len(available) > 3 else available


def available_memory():
    """Respect host and unified cgroup headroom; missing host data fails closed."""
    values = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(values['MemAvailable'].split()[0]) * 1024
    # The process's cgroup may be below the mount root (e.g. a desktop user slice).
    group = next(line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::'))
    root = Path('/sys/fs/cgroup') / group.lstrip('/')
    if '..' in root.parts:
        raise ValueError('Cannot resolve the execution memory cgroup.')
    while root.is_relative_to('/sys/fs/cgroup'):
        ceiling = root / 'memory.max'
        if ceiling.exists():
            limit = ceiling.read_text().strip()
            if limit != 'max':
                available = min(available, max(0, int(limit) - int((root / 'memory.current').read_text())))
        if root == Path('/sys/fs/cgroup'):
            break
        root = root.parent
    return available


def _integer(environment, name, default, minimum, maximum):
    raw = environment.get(name, str(default))
    if not raw.isdecimal() or not minimum <= int(raw) <= maximum:
        raise ValueError(f'{name} must be an integer in {minimum}..{maximum}.')
    return int(raw)


@dataclass(frozen=True)
class Capacity:
    cpu_slots: int
    cpu_memory_bytes: int
    cuda_memory_bytes: int
    reserve_bytes: int
    cores: tuple = field(default_factory=usable_cores)

    @classmethod
    def configured(cls, environment=None):
        environment = os.environ if environment is None else environment
        cores = len(usable_cores())
        return cls(
            _integer(environment, 'TULDOK_CPU_RUN_SLOTS', min(7, cores), 1, 7),
            _integer(environment, 'TULDOK_CPU_RUN_MEMORY_MIB', 1024, 64, 1048576) * MIB,
            _integer(environment, 'TULDOK_CUDA_RUN_MEMORY_MIB', 4096, 64, 1048576) * MIB,
            _integer(environment, 'TULDOK_RUN_MEMORY_RESERVE_MIB', 1024, 64, 1048576) * MIB)

    def claim(self, run):
        recipe = run.get('material', {}).get('recipe', {})
        device = 'cuda' if recipe.get('runtime_device') == 'cuda' else 'cpu'
        resources = recipe.get('resources', {})
        memory = self.cuda_memory_bytes if device == 'cuda' else self.cpu_memory_bytes
        return device, max(memory, resources.get('memory_bytes', 0)), resources.get('cpu_cores', min(2, len(self.cores)) if device == 'cuda' else 1)

    def admits(self, claim, active, available_bytes):
        device, memory_bytes, cores = claim
        maximum = 1 if device == 'cuda' else self.cpu_slots
        return (len(active) < MAX_ATTEMPTS
                and sum(other[0] == device for other in active) < maximum
                and sum(other[2] for other in active) + cores <= len(self.cores)
                and sum(other[1] for other in active) + memory_bytes + self.reserve_bytes <= available_bytes)
