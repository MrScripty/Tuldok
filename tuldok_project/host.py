"""The app's side of a served project folder: credentials, the caller's rule, and refusals as HTTP answers.

Owns section 6 of docs/plans/definition-first-projects/spec-m7.md, apart from
the routes in app.py. A ProjectHost holds the catalog's Metadata and Access
(the credentials the app signs in with, as Dataset does) and one Service for
the folder. dispatch checks the caller's who rule with access.require inside
the credential app.py has bound, passes the caller's identity to the service as
its actor, and turns a ProjectError into a status and a refusal body;
product_file does the same for the bytes of a product's file. This is
the one module of the package that imports the app's kept layers (metadata,
access, agent_api); access errors are left to app.py, which answers them.
"""
from pathlib import Path

import agent_api
from access import Access, AccessError
from metadata import Metadata

from . import local, operations, store
from .service import Service

REFUSAL_PROBLEMS = 50
MESSAGE_CHARACTERS = 1000


def refusal(error):
    """A ProjectError as (status, body): error and code, and problems, references and files when not empty."""
    body = {'error': (str(error) or error.code)[:MESSAGE_CHARACTERS], 'code': error.code}
    if error.problems:
        body['problems'] = [problem if isinstance(problem, dict) else problem.as_dict()
                            for problem in error.problems[:REFUSAL_PROBLEMS]]
    if error.references:
        body['references'] = [str(reference) for reference in error.references]
    if error.files:
        body['files'] = [str(name) for name in error.files]
    return operations.error_status(error.code), body


class ProjectHost:
    """One project folder served by app.py; see the module docstring."""
    project_folder_mode = True

    def __init__(self, data_path, folder, *, dsn=None):
        """Open the catalog of data_path and the folder, and start the build worker; raises ProjectError.

        A settings file that is not valid (local.SettingsError) is raised as
        ProjectError code settings before anything is opened, so app.py ends
        start-up with its message.
        """
        try:
            local.projects_home()
        except local.SettingsError as error:
            raise store.ProjectError(str(error), 'settings') from None
        self.path = Path(data_path).resolve()
        self.db = Metadata(self.path, dsn=dsn)
        self.lock = self.db.lock
        self.access = Access(self.db, self.path)
        try:
            self.service = Service(folder, dsn=dsn)
            self.service.start()
        except BaseException:
            self.db.close()
            raise

    @property
    def folder(self):
        return self.service.folder

    def capabilities(self):
        return agent_api.capabilities(self.db.dataset_id, profile='project_folder')

    def dispatch(self, name, arguments):
        """Run project.<name> for the bound credential; return (status, result or refusal body)."""
        operation = operations.by_name(name)
        if operation is not None:
            self._require(operation.who, 'project.' + name)
        identity = self.access.identity()
        actor = {key: identity[key] for key in ('actor_id', 'kind', 'label', 'scopes')}
        try:
            return 200, self.service.call(name, arguments, actor)
        except store.ProjectError as error:
            return refusal(error)
        except local.SettingsError as error:  # the settings file broke while the app runs
            return refusal(store.ProjectError(str(error), 'settings'))

    def product_file(self, run, address, range_header=None):
        """GET /api/project/file for the bound credential, which must be allowed to inspect (as an inspect
        operation is): (200, inside.FileResponse) or (status, refusal body)."""
        self._require('inspect', 'project.file')
        try:
            return 200, self.service.product_file(run, address, range_header)
        except store.ProjectError as error:
            return refusal(error)

    def _require(self, who, action):
        if who == 'owner':
            self.access.require('approve-execution', action, owner_only=True)
        elif who == 'request':
            self.access.require('inspect', action)
            if 'execute' not in self.access.identity()['scopes']:
                error = AccessError('Requesting a build needs a credential with the execute scope.')
                self.access.denial(error, action)
                raise error
        else:
            self.access.require(who, action)

    def close(self):
        try:
            self.service.close()
        finally:
            self.db.close()
