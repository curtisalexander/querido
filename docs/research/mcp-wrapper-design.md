# MCP thin wrapper — design (proposed 0.3.0 headline)

Status: design draft, 2026-07-06. Promoted from the PLAN.md candidate list;
not yet committed work. Read DIFFERENTIATION.md's "filter for future changes"
before implementing.

## Why now

The CLI is already MCP-ready by design: stable flags, structured `-f json`
envelopes with `next_steps`, structured error codes with `try_next`, and no
TTY-required paths. An MCP server makes qdo reachable from every MCP client
(Claude Code, Claude Desktop, Continue, Zed, …) without the client having to
know CLI conventions — and it is the natural launch headline for 0.3.0 after
the quiet 0.2.0 PyPI debut: "the persistent-memory layer for data
exploration, now an MCP server."

## Fit with the invariants

- **No daemon.** An MCP stdio server is spawned and owned by the client per
  session, like any subprocess. Nothing listens on a port; nothing outlives
  the client. This is an adapter, not a service. (SSE/HTTP transport is
  explicitly out of scope.)
- **Deterministic tools.** The server adds zero intelligence — it maps tool
  calls to the same deterministic command layer.
- **One CLI surface.** The server is reached via `qdo mcp serve` (a new
  command group, not a second binary), and every tool is a 1:1 mapping onto
  an existing command. No tool exists that the CLI can't do.
- **Pay for what you use.** New extra: `querido[mcp]` pulling the `mcp`
  Python SDK. `qdo mcp serve` without the extra gives the standard
  `MISSING_DEPENDENCY` error with the install hint. All imports lazy.

## Shape

### Execution model: subprocess per tool call

Each tool call shells out to `qdo -f json <cmd> ...` exactly like the
workflow runner does (reuse its argv assembly + `querido._argv` hoist).

- Guarantees CLI parity forever — the eval, docs, and MCP surface can never
  drift apart, because there is only one implementation.
- Inherits the structured error envelope and exit-code contract for free.
- Startup cost (~70 ms) is negligible against any real query.
- In-process dispatch is a possible later optimization; do not start there.

### Tool surface: small and curated, not 32 tools

Exposing every command as a tool burns client context and drowns agents in
choices — the same reason SKILL.md promotes a core loop rather than the full
surface. v1 tools (names tentative, ~9):

| Tool | Maps to | Notes |
|------|---------|-------|
| `qdo_catalog` | `catalog` | discover |
| `qdo_context` | `context` | the anchor; stored metadata auto-merged |
| `qdo_query` | `query` | read-only; no `--allow-write` in v1 |
| `qdo_values` | `values` | enum discovery |
| `qdo_quality` | `quality` | rule-checking against stored metadata |
| `qdo_profile` | `profile` | stats drill-down |
| `qdo_metadata_search` | `metadata search` | find what's already known |
| `qdo_capture` | `<cmd> --write-metadata` / `metadata suggest --apply` | the compounding-loop write half |
| `qdo_assert` | `assert` | verification primitive |

Every tool returns the JSON envelope verbatim — `next_steps` included, which
is the differentiator speaking MCP natively: each tool result tells the agent
what to do next. Connection comes from an env-var default
(`QDO_MCP_CONNECTION`) plus a per-call `connection` parameter.

### v2 candidates (explicitly not v1)

- MCP **resources**: expose `.qdo/metadata/**/*.yaml` as readable resources
  (the knowledge base as browsable context, not tool calls).
- `qdo_bundle_inspect` / workflow-run tools.
- Write-enabled `qdo_query` behind an explicit server flag.

## Safety

- Read-only always in v1: the server never passes `--allow-write`, and
  `QDO_SESSION` recording is opt-in via the server's environment.
- Table/column identifier validation, read-only URI modes, and the
  destructive-SQL guard are all inherited from the CLI — no new SQL surface.

## Testing and eval

- Unit tests with the `mcp` SDK's in-memory client transport: every tool
  call → envelope shape, error mapping (`TABLE_NOT_FOUND` → MCP tool error
  with the same code), missing-extra behavior.
- Extend the self-hosting eval with an MCP variant (Claude Code client
  config pointing at `qdo mcp serve`) on a subset of the 15 tasks. The
  existing 45/45 CLI baseline stays the primary gate.

## Sizing

Roughly: `cli/mcp.py` (serve command) + `core/mcp_server.py` (tool
definitions + subprocess dispatch) + tests + README/SKILL sections. The
subprocess model means no per-command adapters — one dispatch function and a
declarative tool table. Estimate: comparable to the `assert` + `agent`
commands combined, well under the workflow engine.

## Open questions (decide before building)

1. Tool naming: `qdo_*` prefix vs bare names — check what reads best in
   Claude Code's tool list next to other servers.
2. Should `qdo_capture` be one tool with a `mode` parameter or two tools
   (`suggest_apply` vs `write_from_scan`)? Leaning one tool, mirroring the
   CLI's `--write-metadata` mental model.
3. Whether `qdo mcp serve` should auto-detect `.qdo/` in cwd and preload the
   connection list into the server's instructions string.
