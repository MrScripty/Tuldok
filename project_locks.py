"""Preserve host -> project session -> projection command lock ordering."""
from contextlib import contextmanager, ExitStack
import threading
import time

from metadata import CATALOG_LOCAL_TIMEOUT, CatalogBusy


class ProjectLock:
    """CatalogLock interface for owners that begin at the projection lock.

    Owners retain the actual PostgreSQL advisory lock and its deadlines. Every
    entry also owns the host authorization connection before the project
    session, including background workers which have no foreground request.
    """
    def __init__(self, host, session, projection):
        self.host, self.session, self.projection = host, session, projection
        self._local = threading.local()

    @property
    def depth(self):
        return self.projection.depth

    @property
    def mutex(self):
        return self.projection.mutex

    @property
    def owned_by_current_thread(self):
        return bool(getattr(self._local, 'stacks', ()) or getattr(self._local, 'bounded_depth', 0))

    def __enter__(self):
        stack = ExitStack()
        try:
            stack.enter_context(self.host)
            if not self.session.acquire(timeout=CATALOG_LOCAL_TIMEOUT):
                raise CatalogBusy('Project command ownership did not become available within its local wait bound.')
            stack.callback(self.session.release)
            stack.enter_context(self.projection)
            if not hasattr(self._local, 'stacks'):
                self._local.stacks = []
            self._local.stacks.append(stack)
            return self
        except BaseException:
            stack.close()
            raise

    def __exit__(self, kind, error, tb):
        return self._local.stacks.pop().__exit__(kind, error, tb)

    @contextmanager
    def bounded(self, deadline, cancelled=None):
        with ExitStack() as stack:
            stack.enter_context(self.host.bounded(deadline, cancelled))
            while not self.session.acquire(timeout=min(.1, max(0, deadline-time.monotonic()))):
                if (cancelled and cancelled()) or time.monotonic() >= deadline:
                    raise CatalogBusy('Project command ownership reached its recovery deadline.')
            stack.callback(self.session.release)
            if (cancelled and cancelled()) or time.monotonic() >= deadline:
                raise CatalogBusy('Project command ownership was cancelled or reached its recovery deadline.')
            stack.enter_context(self.projection.bounded(deadline, cancelled))
            self._local.bounded_depth = getattr(self._local, 'bounded_depth', 0) + 1
            try:
                yield self
            finally:
                self._local.bounded_depth -= 1
