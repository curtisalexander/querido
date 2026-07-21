"""``next_steps`` rules for error recovery and workflow-step failures."""

from __future__ import annotations

from querido.core.next_steps._helpers import _step


def for_error(
    code: str,
    *,
    connection: str | None = None,
    table: str | None = None,
) -> list[dict]:
    """Rules for ``try_next`` on structured errors.

    Connection/table may be unknown at error time (e.g. validation failed
    before they were resolved) — rules skip suggestions that need missing
    context.
    """
    steps: list[dict] = []

    if code == "TABLE_NOT_FOUND" and connection:
        argv = ["qdo", "catalog", "-c", connection]
        if table:
            argv += ["--pattern", table]
        steps.append(_step(argv, "List visible tables (optionally filtered)."))
        steps.append(
            _step(
                ["qdo", "cache", "sync", "-c", connection],
                "Refresh the metadata cache if the table was just created.",
            )
        )

    elif code == "COLUMN_NOT_FOUND" and connection and table:
        steps.append(
            _step(
                ["qdo", "inspect", "-c", connection, "-t", table],
                "See the available columns on the target table.",
            )
        )

    elif code == "DATABASE_LOCKED":
        steps.append(
            _step(
                ["qdo", "config", "list"],
                "Check which connections might be holding a lock.",
            )
        )

    elif code == "DATABASE_OPEN_FAILED" and connection:
        steps.append(
            _step(
                ["qdo", "config", "test", connection],
                "Verify the connection's path or credentials.",
            )
        )

    elif code == "AUTH_FAILED" and connection:
        steps.append(
            _step(
                ["qdo", "config", "test", connection],
                "Re-authenticate and verify the connection.",
            )
        )

    elif code == "MISSING_DEPENDENCY":
        steps.append(
            {
                "cmd": "uv pip install 'querido[duckdb]'",
                "why": "Install the DuckDB + Parquet extra.",
            }
        )
        steps.append(
            {
                "cmd": "uv pip install 'querido[snowflake]'",
                "why": "Install the Snowflake extra.",
            }
        )

    elif code == "FILE_NOT_FOUND":
        steps.append(
            _step(["qdo", "config", "list"], "List configured connections to find the right path.")
        )

    elif code == "SESSION_NOT_FOUND":
        steps.append(
            _step(
                ["qdo", "session", "list"],
                "List recorded sessions to find the right name.",
            )
        )

    elif code == "SESSION_STEP_UNSTRUCTURED":
        steps.append(
            _step(
                [
                    "QDO_SESSION=<name>",
                    "qdo",
                    "-f",
                    "json",
                    "query",
                    "-c",
                    "<connection>",
                    "--sql",
                    "<sql>",
                ],
                "Re-record the source step with -f json so --from can replay its SQL envelope.",
            )
        )
        steps.append(
            _step(
                ["qdo", "session", "show", "<session>"],
                "Inspect the session to find a step already recorded as JSON.",
            )
        )

    elif code in {
        "SESSION_STEP_NOT_FOUND",
        "SESSION_STEP_UNSUPPORTED",
        "SESSION_STEP_NO_SQL",
        "SESSION_STEP_REF_INVALID",
    }:
        steps.append(
            _step(
                ["qdo", "session", "show", "<session>"],
                "Inspect the session and pick a recorded query step reference.",
            )
        )

    elif code == "SESSION_SNAPSHOT_NOT_FOUND":
        if connection and table:
            steps.append(
                _step(
                    ["qdo", "-f", "json", "inspect", "-c", connection, "-t", table],
                    "Record a structured snapshot before diffing against a session.",
                )
            )
        steps.append(
            _step(
                ["qdo", "session", "show", "<session>"],
                "Inspect the session to confirm it captured this table in structured form.",
            )
        )

    elif code == "METADATA_NOT_FOUND" and connection and table:
        steps.append(
            _step(
                ["qdo", "metadata", "init", "-c", connection, "-t", table],
                "Create the metadata YAML before trying to read it.",
            )
        )

    elif code == "COLUMN_SET_NOT_FOUND" and connection and table:
        steps.append(
            _step(
                ["qdo", "config", "column-set", "list", "-c", connection, "-t", table],
                "List saved column sets for this table.",
            )
        )

    elif code == "SNOWFLAKE_REQUIRED":
        steps.append(
            _step(
                ["qdo", "config", "list"],
                "List configured connections and pick a Snowflake one.",
            )
        )

    elif code == "WRITE_REQUIRES_ALLOW_WRITE":
        steps.append(
            {
                "cmd": "qdo query --allow-write -c <connection> --sql '<write statement>'",
                "why": "Re-run only if you intend to mutate data.",
            }
        )
        steps.append(
            {
                "cmd": "qdo query -c <connection> --sql 'select ...'",
                "why": "Keep using the default read-only path for inspection queries.",
            }
        )

    elif code == "CONNECTION_NOT_FOUND":
        steps.append(
            _step(
                ["qdo", "config", "list"],
                "List configured connections to find the right source name.",
            )
        )

    return steps


def for_workflow_step_failed(
    *,
    workflow: str,
    step_id: str,
    step_cmd: str,
    session: str,
    timed_out: bool = False,
) -> list[dict]:
    """Rules for ``try_next`` on a workflow step failure.

    Deterministic follow-ups: stream the session to see what else happened,
    re-run with ``--verbose`` for live output, or run the failing step's
    command standalone to iterate on it outside the workflow.
    """
    steps: list[dict] = []

    if session:
        steps.append(
            _step(
                ["qdo", "session", "show", session],
                "See every step this run recorded (step-by-step stdout is saved).",
            )
        )

    if step_cmd:
        steps.append(
            {
                "cmd": step_cmd,
                "why": (
                    f"Re-run step {step_id!r} on its own to iterate "
                    "without the rest of the workflow."
                ),
            }
        )

    steps.append(
        _step(
            ["qdo", "workflow", "run", workflow, "--verbose"],
            "Re-run with --verbose to stream each step's stdout as it executes.",
        )
    )

    if timed_out:
        steps.append(
            _step(
                ["qdo", "workflow", "run", workflow, "--step-timeout", "0"],
                "Disable the step timeout for a one-off run (agents: use with care).",
            )
        )

    return steps
