# P6 shared interface observation qualification

P6 implements the opt-in `interface_observation_v2` sink at the actual HTTP,
CLI and MCP boundaries. It does not activate recording on an installation. V1
stores, launch selection and reader defaults remain supported unchanged. V2
requires an explicitly selected fresh private store and exact operator reader
version. The [persisted/operator contract](../../../contracts/mcp-observer.md#shared-interface-observation-v2)
owns privacy, lifecycle and resource semantics.

The canonical implementation operation is P6 of
`docs/plans/end-to-end-model-development/reports/implementation-handoff.md`,
with the D2 observation section of `agent-interfaces-observability.md`. The later
user implementation authorization supersedes the handoff's original design-only
pause. This isolated proposal starts at P2 `069298e`, branch
`feature/model-development-p6`, worktree `/workspace/Tuldok-p6`; the parent owns
serial integration into the complete model-development product. Retain this
clean worktree and draft branch for that integration/review; no merge or cleanup
is requested here.

## Behavior and evidence boundary

One shared observer owner handles exact schema identity, private SQLite access,
retention, bounded projections, stages and independent operator health. HTTP
observations wrap `make_handler`, CLI observations wrap command entry and actual
AgentClient request dispatch, and MCP observations retain the real SDK bridge's
framing/admission/dispatch/return/writer seams. New selected public contract
identity is local code identity, never a hash of request/domain material. No
actor/catalog/Run/material/request/grant/artifact identity, raw values, nested
keys or error text reaches the passive store. There are no inferred causal
links between HTTP and wrapper interactions and no new domain process log.

The implemented request/handler stages do not stand in for domain admission,
commit, child completion or client receipt. HTTP and CLI use actual write loops
with known partial-byte counts; MCP preserves its five-second bounded writer.
Required audit remains transactional and separate. Storage failure or broken
health emission degrades observation alone, without retrying or changing the
ordinary operation result. Normal shutdown marks known unfinished interactions
unknown/incomplete, while killed or failed sessions remain unmatched on reopen.

`tests/test_interface_observation.py` contains the real interface/storage matrix,
private schema/retention/shape checks, socket/stdout partial-delivery tests, and
real PostgreSQL Access/Runs tests. The latter submits one exact actor/key/body
through each passive storage state and proves one Run receipt. It then fails
required Access audit, proves a structured storage refusal and no new Run, and
reuses the same unconsumed one-use grant after the failure is removed. The CLI
reconciles that receipt with the real 201 status preserved in its passive event.
Authored owners in the other transport tests are explicitly transport evidence,
not substitutes for this transaction evidence or model workflow acceptance.

## Local qualification environment and commands

Linux 6.18.44 x86-64, Python 3.12.14, SQLite 3.53.1, PostgreSQL 17.11,
MCP 1.30.0 and jsonschema 4.26.0. The shared environment exposes five logical
CPUs with a four-CPU cgroup quota and 16 GiB memory. Optional dependencies were
explicitly provisioned under `/workspace/tuldok-runtime`; observation code does
not install dependencies, start PostgreSQL or configure a collector. All stores
used for qualification are disposable private fixtures.

```sh
# Supply the isolated PostgreSQL URL through TULDOK_DATABASE_URL.
PYTHONPATH=.:tests /workspace/tuldok-runtime/bin/python -m unittest \
  test_mcp_observer test_mcp_stdio test_interface_observation test_agent_project_cli -v
/workspace/tuldok-runtime/bin/python -m unittest discover -s tests -p test_agent_api.py -v
PYTHONPATH=.:tests /workspace/tuldok-runtime/bin/python -c \
  'import json; from test_interface_observation import measure_overhead; print(json.dumps(measure_overhead(), indent=2))'
```

The optional-agent CI environment now runs both observer suites, so real SDK
cases are not only encountered by the base interpreter that skips optional MCP.
The frozen legacy tool-definition assertion explicitly projects the retained v1
operations, avoiding a stale whole-new-registry comparison introduced by P2.
The observer test read allowance is 20 seconds for startup under concurrent CPU
load; the product writer deadline remains five seconds. Earlier simultaneous
training and boundary runs exceeded the old eight-second test startup allowance;
serial final qualification is reported separately from those failed attempts.

Final verification and current measurements are recorded below.
No H1–H7 model-training, browser or package-closure completion is claimed by this
transport slice. The parent owns those integrated gates and the exact final
product revision. The large official-SDK artifact-transfer failure found in unchanged P2 is
resolved by the bounded pipe change qualified below. Unsupported capacity or a
stalled reader still produces unknown delivery, not a fabricated success.

## Standards and write set

Coding Standards Core and Router at `dcc56f26` select implementation,
verification/oracle, commit, documentation and tooling workflows; launcher, IPC
and persistence profiles; contracts/protocol/evolution, diagnostics, security, concurrency, resilience,
performance and code-ownership guidance for these actual changes. No
language/framework profile is inferred for Python. Public retained contract and
later user implementation instructions govern compatibility and authorization.

Write set: `mcp_observer.py`, `mcp_stdio.py`, `agent_api.py`, `app.py`,
`project_cli.py`, `tests/test_mcp_observer.py`, `tests/test_mcp_stdio.py`, new
`tests/test_interface_observation.py`, the three affected interface contracts,
this report, and two directly affected CI test entrypoints. No domain schema,
Run lifecycle, grant policy, registry operation schema or model producer is
changed by P6. The additional stdout pipe capacity is owned by the existing MCP
transport and does not change its wire representation or writer deadline.

## Final local results

- The serial combined observer/protocol/interface/real-CLI run passed **68 tests**
  in 259.623 seconds. The Agent API suite separately passed **17 tests**.
- After the large HTTP byte-counter refinement, both focused large-counter and
  actual PostgreSQL receipt/audit/CLI-201 tests passed. V2 counters cover up to
  1 GiB; the v1 32 MiB counter bound is unchanged.
- After the pipe change, the full protocol suite plus actual stalled-reader
  tests under v1 and v2 passed **20 tests** in 42.030 seconds. This includes
  refused/unsupported capacity handling and preservation of known partial bytes.
- The exact 8 MiB selected HTTP + official-SDK MCP transfer passed with recording
  disabled, and again with the explicit v2 store. Both reconstruct and compare
  all 8,388,608 bytes through existing whole/segment hash-bound custody.
- Compilation and whitespace checks passed. Hosted CI and final product-head
  integration remain pending; this branch does not claim those ran.

### Large-frame throughput diagnosis and bounded repair

The original P2 failure reproduced with a successful return at 3437.157 ms but
unknown/incomplete delivery at 8573.406 ms: only 22,216,704 frame bytes had been
accepted before the existing five-second writer deadline. Source inspection
showed the official MCP 1.30 reader concatenates and splits a growing newline
buffer; the artifact envelope appears as both JSON text and structured content.
Changing only bounded local kernel capacity avoids premature writer backpressure
without altering the wire, artifact size, SDK source or five-second deadline.

The actual official-SDK bridge pipe grew from **65,536 to 1,048,576 bytes**; the
measured setup call cost **0.026492 ms**. V2 recorded successful return at
2531.952 ms and complete successful terminal at 5819.366 ms, with exactly
**22,370,675 accepted frame bytes**. The elapsed terminal time includes the HTTP
call and encoding; it is not the writer deadline interval. These are local
representative results, not a slow-client receipt or universal throughput promise.
A refused resize preserves inherited capacity and the ordinary unknown/incomplete
delivery contract. Normal operation has one active SDK request and one serialized
writer; capacity is requested only for that stdout FIFO. No global pipe policy,
SDK install or collector activation changes.

### Disposable v2 boundary measurements

Five samples per mode call `context.get` through the real HTTP handler and client,
the real CLI main/client/stdout file descriptor, or a real MCP SDK bridge and pipe.
HTTP and MCP use an already bootstrapped session; CLI includes a fresh private
config read and authenticated client bootstrap each invocation. Recorder/process
creation is outside each sample. Inputs are empty; responses are the small
authored context fixture. Modes run sequentially on this shared host, so cache
and concurrent-work variability remain; these are observed end-to-end comparisons,
not isolated causal recorder costs or a latency budget.

| Boundary | Disabled median / range (ms) | Healthy median / range (ms) | Median difference (ms) |
| --- | --- | --- | --- |
| http | 17.163 / 14.692–18.631 | 18.858 / 17.455–23.534 | +1.695 |
| cli | 2064.427 / 2031.565–2119.278 | 3145.474 / 2489.917–6140.701 | +1081.047 |
| mcp | 11.773 / 11.530–12.375 | 9.026 / 7.829–11.185 | -2.747 |

Disabled modes created zero store bytes. Every healthy store was 40,960 bytes
and had matching retained starts/terminals, zero unfinished: HTTP 8, CLI 5, MCP 6
(the sessions include their own initialization/discovery observations). Count
retention is qualified at 16 retained starts; expired records remain unchanged
on read-only inspection and are pruned by explicit offline maintenance. All new
stores are mode 0600 in private directories.

The negative MCP difference is measurement variability, not an improvement claim.
CLI bootstrap variability (including one 6140.701 ms healthy sample) prevents an
isolated recorder-overhead or guaranteed-budget claim. The comparison remains
reported; no guessed threshold, zero-cost claim or automatic activation follows.
SQLite's 20 ms contention timeout does not bound filesystem, scheduler or health
stream latency. Operators must qualify their own deployment/storage policy.


Independent review identified and repaired a CLI failure-channel compatibility
issue: the operator stderr health convention would have added two lines around
the CLI's single JSON failure document. Configured CLI observation now keeps its
health emission quiet, including invalid policy; its independent operator reader
remains separate. A real subprocess comparison covers disabled, healthy,
unavailable, unsafe, corrupt and invalid-policy modes and requires byte-identical
stdout/stderr/exit status plus one parseable JSON failure. HTTP/MCP retain their
existing stderr health channel. This is a command-contract preservation fix, not
a change to domain outcomes or passive projection.

The final CLI health-channel follow-up passed all three focused tests in 7.979
seconds: byte-identical subprocess failure diagnostics, actual CLI partial stdout
and actual MCP main/v2 health. The latter confirms MCP's operator stderr channel
was preserved while CLI's machine diagnostic channel remains a single document.
