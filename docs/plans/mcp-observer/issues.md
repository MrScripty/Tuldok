# Findings and dispositions

- **Blocking dependency:** Coding-Standards #3 qualified commit/source and acceptance
  evidence are pending from parent. Do not adapt an unqualified draft or invent
  a competing storage/event contract. Owner: parent; next action: supply qualified
  reference, inspect against Tuldok boundaries, then admit adaptation.
- **Correlation constraint:** duplicate in-flight JSON-RPC IDs and valid later ID
  reuse rule out correlation by raw client ID alone. Owner: observer adapter;
  disposition: added direct baseline regression cases, include in final design.
- **Environment:** initial workspace had no optional MCP/jsonschema/psycopg
  environment or PostgreSQL server. Owner: task; disposition: isolated pinned SDK
  environment installed at `/workspace/issue59-agent-env`; disposable PostgreSQL
  fixture preparation recorded in baseline evidence. No existing installation changed.
