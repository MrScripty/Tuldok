"""Explicit test actors using production bootstrap, exchange, and token binding.

No Dataset constructors or HTTP handlers are patched. Callers choose every owner
context and authenticated request; anonymous requests remain anonymous.
"""
from contextlib import contextmanager
from urllib.request import Request


class ExplicitOwnerFixture:
    def __init__(self, catalog_id, token, identity):
        self.catalog_id = catalog_id
        self.token = token
        self.identity = identity

    @classmethod
    def bootstrap(cls, dataset):
        result = dataset.access.exchange(dataset.access._local_owner_token())
        return cls(dataset.db.dataset_id, result['token'], result['identity'])

    @contextmanager
    def bound(self, dataset):
        if dataset.db.dataset_id != self.catalog_id:
            raise ValueError('Owner fixture belongs to another catalog.')
        with dataset.access.bind(self.token):
            yield self

    @property
    def headers(self):
        return {'Authorization': 'Bearer ' + self.token}

    def request(self, url, data=None, headers=None, method=None):
        return Request(url, data=data, headers={**self.headers, **(headers or {})}, method=method)


def bind_owner(testcase, dataset):
    """Explicit setUp admission; reuse the credential for a reopened catalog."""
    owners = getattr(testcase, '_explicit_owner_fixtures', None)
    if owners is None:
        owners = testcase._explicit_owner_fixtures = {}
    fixture = owners.get(dataset.db.dataset_id)
    if fixture is None:
        fixture = owners[dataset.db.dataset_id] = ExplicitOwnerFixture.bootstrap(dataset)
    testcase.enterContext(fixture.bound(dataset))
    return fixture


def execute_admitted(dataset, run_id):
    """Drive a queued test run using its unchanged real admission envelope."""
    with dataset.lock:
        run = dataset.runs._load(run_id)
    with dataset.access._job('runs', run_id, run['admission_id'], run['request_sha256']):
        dataset.runs._execute(run_id)
