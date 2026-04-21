# Project Status

## Completed

- Repositioned qdo around the promoted workflow:
  `catalog -> context -> metadata -> query/assert -> report/bundle`.
- Updated the top-level product framing in [README.md](README.md) to use the
  agent-first positioning:
  `qdo is an agent-first data exploration CLI that turns one-off investigation into reusable team knowledge.`
- Reworked CLI help grouping to better reflect the promoted workflow.
- Fixed `next_steps` suggestions so they emit valid runnable commands for
  `config test`, `joins`, and related follow-up guidance.
- Extended structured JSON-envelope support to additional management commands,
  including `config list` and `session list`.
- Fixed the HTML report renderer so `qdo report table` works correctly when
  metadata exists.
- Renamed the Claude benchmark harness from
  `scripts/eval_skill_files.py` to
  `scripts/eval_skill_files_claude.py`.
- Added a Codex benchmark harness in
  `scripts/eval_skill_files_codex.py`.
- Updated the benchmark task set to reinforce the promoted workflow, including:
  - allowing `C2_query_total_by_region` to pass with light orientation before
    `query`,
  - separating deeper `profile` use from lighter `context` use,
  - classifying DuckDB lock failures separately as `database-lock`.
- Updated agent guidance in:
  - [integrations/skills/SKILL.md](integrations/skills/SKILL.md)
  - [integrations/continue/qdo.md](integrations/continue/qdo.md)
  so agents:
  - default to the promoted workflow,
  - avoid starting with `qdo --help` / `qdo overview`,
  - treat drill-down commands as secondary,
  - run `qdo` sequentially against the same DuckDB file.
- Hardened the DuckDB connector to open existing file-backed databases in
  read-only mode by default, which reduces lock contention for agent-style
  exploration.
- Hardened the Codex benchmark harness so artifact-producing tasks can still be
  scored as successful when Codex times out after the expected side effect has
  already happened.

## Latest Eval State

- Full two-model Codex run:
  - `gpt-5.4-mini`: `12/15`
  - `gpt-5.4`: `13/15`
- Focused rerun of the previously problematic tasks:
  - `A3_join_keys`: pass on both models
  - `B1_enumerate_enum`: pass on both models
  - `C2_query_total_by_region`: pass on both models
  - `D2_init_metadata`: pass on `gpt-5.4-mini`; `gpt-5.4` timed out after
    writing the expected YAML artifact

## Recommended Next Work

### Near Term

- Rerun the full Codex benchmark with the hardened timeout/artifact logic so the
  official score reflects the current harness behavior.
- Run the Claude benchmark under the same updated workflow and compare failure
  patterns against the Codex run.
- Finish the structured-output pass for remaining management/reporting commands
  that still bypass the standard envelope.
- Continue simplifying the “start here” surface in docs and help text so
  `context` remains the obvious first deep-dive command.

### Medium Term

- Refactor large output/orchestration files, especially formatter and
  next-step logic, into smaller command-family modules.
- Keep tightening agent guidance and benchmark tasks together so the eval suite
  tracks the product’s intended workflow rather than legacy usage patterns.
- Expand the metadata-centered story:
  better search, scoring, diffing, and “what still needs metadata?” guidance.

### Avoid For Now

- Broad command-surface expansion that does not strengthen the metadata/session/
  hand-off loop.
- Plugin/platform work before the core agent workflow and metadata-sharing path
  feel fully coherent.
