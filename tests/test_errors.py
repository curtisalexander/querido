"""Tests for error messages, fuzzy suggestions, and input validation across the CLI."""

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def _seed_session_step(
    cwd: Path,
    *,
    name: str,
    index: int,
    payload: dict | str,
    command: str = "query",
) -> None:
    session_dir = cwd / ".qdo" / "sessions" / name
    step_dir = session_dir / f"step_{index}"
    step_dir.mkdir(parents=True, exist_ok=True)

    stdout_path = step_dir / "stdout"
    if isinstance(payload, str):
        stdout_path.write_text(payload, encoding="utf-8")
    else:
        stdout_path.write_text(json.dumps(payload), encoding="utf-8")

    steps_path = session_dir / "steps.jsonl"
    record = {
        "index": index,
        "timestamp": "2026-04-22T00:00:00+00:00",
        "cmd": f"qdo {command}",
        "args": [command],
        "duration": 0.1,
        "exit_code": 0,
        "stdout_path": str(stdout_path.relative_to(cwd / ".qdo")),
    }
    with steps_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_path(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
    conn.execute("CREATE TABLE orders (id INTEGER, user_id INTEGER, total REAL)")
    conn.execute("CREATE TABLE products (id INTEGER, product_name TEXT, price REAL)")
    conn.execute("CREATE TABLE user_roles (user_id INTEGER, role TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 'alice@test.com')")
    conn.execute("INSERT INTO orders VALUES (1, 1, 99.99)")
    conn.execute("INSERT INTO products VALUES (1, 'Widget', 9.99)")
    conn.execute("INSERT INTO user_roles VALUES (1, 'admin')")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def duckdb_path(tmp_path: Path) -> str:
    import duckdb

    db_path = str(tmp_path / "test.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, age INTEGER)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Validation-error contract
# ---------------------------------------------------------------------------
#
# Validation errors still use Typer's human-facing prose path in rich mode, but
# the important agent-facing cases now emit structured errors under
# ``--format json`` / ``--format agent``. Rich-mode tests below therefore keep
# asserting on user-visible content, while the JSON-specific tests assert on
# the stable machine-readable error contract.
#
# Every validation error must: exit non-zero, not leak a Python traceback,
# and echo the offending identifier back to the user.


@pytest.mark.parametrize(
    ("argv", "expected_identifier"),
    [
        (["inspect", "-t", "nonexistent"], "nonexistent"),
        (["preview", "-t", "nonexistent"], "nonexistent"),
        (["profile", "-t", "nonexistent"], "nonexistent"),
        (["dist", "-t", "nonexistent", "-C", "id"], "nonexistent"),
        (["sql", "select", "-t", "nonexistent"], "nonexistent"),
        (["dist", "-t", "users", "-C", "nonexistent"], "nonexistent"),
    ],
    ids=[
        "inspect-missing-table",
        "preview-missing-table",
        "profile-missing-table",
        "dist-missing-table",
        "sql-select-missing-table",
        "dist-missing-column",
    ],
)
def test_validation_error_contract(
    sqlite_path: str, argv: list[str], expected_identifier: str
) -> None:
    """Non-zero exit, no traceback, offending identifier echoed back."""
    result = runner.invoke(app, [*argv, "-c", sqlite_path])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert expected_identifier in result.output


def test_profile_column_filter_missing(sqlite_path: str) -> None:
    """``profile --columns nonexistent`` has a distinct error path that says
    "No matching columns" rather than echoing the bad identifier verbatim.
    Kept as a separate test so the product can change without failing the
    main validation contract above.
    """
    result = runner.invoke(
        app, ["profile", "-c", sqlite_path, "-t", "users", "--columns", "nonexistent"]
    )
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "No matching columns" in result.output or "nonexistent" in result.output


def test_table_not_found_lists_available(sqlite_path: str) -> None:
    """The list of available tables shows up when one isn't found."""
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "nonexistent"])
    assert result.exit_code != 0
    assert "users" in result.output


def test_column_not_found_lists_available(sqlite_path: str) -> None:
    """The list of available columns shows up when one isn't found."""
    result = runner.invoke(app, ["dist", "-c", sqlite_path, "-t", "users", "-C", "nonexistent"])
    assert result.exit_code != 0
    assert "name" in result.output or "id" in result.output


def test_missing_connection_file_contract(tmp_path: Path) -> None:
    """Missing DB file: non-zero, no traceback, suggests `qdo config add`."""
    missing = str(tmp_path / "missing.db")
    result = runner.invoke(app, ["inspect", "-c", missing, "-t", "users"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    # ``qdo config add`` is the try_next hint surfaced to the user — stable
    # wording, worth asserting on until R.22/R.23 route this through the
    # structured envelope.
    assert "qdo config add" in result.output


def test_validation_error_json_table_not_found_uses_structured_error(sqlite_path: str) -> None:
    result = runner.invoke(app, ["-f", "json", "inspect", "-c", sqlite_path, "-t", "nonexistent"])
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["error"] is True
    assert payload["code"] == "TABLE_NOT_FOUND"
    assert "nonexistent" in payload["message"]
    assert any("qdo catalog" in step["cmd"] for step in payload["try_next"])


def test_validation_error_json_column_not_found_uses_structured_error(sqlite_path: str) -> None:
    result = runner.invoke(
        app,
        ["-f", "json", "dist", "-c", sqlite_path, "-t", "users", "-C", "nonexistent"],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["error"] is True
    assert payload["code"] == "COLUMN_NOT_FOUND"
    assert "nonexistent" in payload["message"]
    assert any("qdo inspect" in step["cmd"] for step in payload["try_next"])


def test_validation_error_json_session_not_found_uses_structured_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["-f", "json", "session", "show", "nope"])
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["error"] is True
    assert payload["code"] == "SESSION_NOT_FOUND"
    assert any("qdo session list" in step["cmd"] for step in payload["try_next"])


def test_validation_error_json_query_from_session_step_not_found(
    sqlite_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["-f", "json", "query", "-c", sqlite_path, "--from", "scratch:7"])
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["code"] == "SESSION_NOT_FOUND"


def test_validation_error_json_query_from_session_step_missing_index(
    sqlite_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_session_step(
        tmp_path,
        name="scratch",
        index=1,
        payload={"command": "query", "data": {"sql": "select 1"}, "next_steps": [], "meta": {}},
    )

    result = runner.invoke(app, ["-f", "json", "query", "-c", sqlite_path, "--from", "scratch:7"])
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["code"] == "SESSION_STEP_NOT_FOUND"
    assert any("qdo session show" in step["cmd"] for step in payload["try_next"])


def test_validation_error_json_query_from_session_step_unstructured(
    sqlite_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_session_step(tmp_path, name="scratch", index=1, payload="plain text output")

    result = runner.invoke(app, ["-f", "json", "query", "-c", sqlite_path, "--from", "scratch:1"])
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["code"] == "SESSION_STEP_UNSTRUCTURED"


def test_validation_error_json_query_from_session_step_unsupported_command(
    sqlite_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_session_step(
        tmp_path,
        name="scratch",
        index=1,
        payload={"command": "catalog", "data": {}, "next_steps": [], "meta": {}},
        command="catalog",
    )

    result = runner.invoke(app, ["-f", "json", "query", "-c", sqlite_path, "--from", "scratch:1"])
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["code"] == "SESSION_STEP_UNSUPPORTED"


def test_validation_error_json_query_from_session_step_missing_sql(
    sqlite_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_session_step(
        tmp_path,
        name="scratch",
        index=1,
        payload={"command": "query", "data": {}, "next_steps": [], "meta": {}},
    )

    result = runner.invoke(app, ["-f", "json", "query", "-c", sqlite_path, "--from", "scratch:1"])
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["code"] == "SESSION_STEP_NO_SQL"


def test_validation_error_json_query_from_session_step_invalid_ref(
    sqlite_path: str,
) -> None:
    result = runner.invoke(app, ["-f", "json", "query", "-c", sqlite_path, "--from", "scratch"])
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["code"] == "SESSION_STEP_REF_INVALID"


def test_validation_error_json_metadata_not_found_uses_structured_error(
    sqlite_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "show", "-c", sqlite_path, "-t", "users"],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["error"] is True


def test_validation_error_json_metadata_undo_not_available(
    sqlite_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "undo", "-c", sqlite_path, "-t", "users"],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["code"] == "METADATA_UNDO_NOT_AVAILABLE"


def test_validation_error_json_metadata_undo_drift(
    sqlite_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import yaml

    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])
    meta_file = tmp_path / ".qdo" / "metadata" / "test" / "users.yaml"
    meta = yaml.safe_load(meta_file.read_text())
    meta["notes"] = "manual drift"
    meta_file.write_text(yaml.safe_dump(meta, sort_keys=False))

    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "undo", "-c", sqlite_path, "-t", "users"],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["code"] == "METADATA_UNDO_DRIFT"


def test_validation_error_json_column_set_not_found_uses_structured_error(
    sqlite_path: str,
) -> None:
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "profile",
            "-c",
            sqlite_path,
            "-t",
            "users",
            "--column-set",
            "missing",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["error"] is True
    assert payload["code"] == "COLUMN_SET_NOT_FOUND"
    assert any("qdo config column-set list" in step["cmd"] for step in payload["try_next"])


def test_validation_error_json_sql_required_uses_structured_error(sqlite_path: str) -> None:
    result = runner.invoke(app, ["-f", "json", "assert", "-c", sqlite_path])
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["error"] is True
    assert payload["code"] == "SQL_REQUIRED"


def test_validation_error_json_write_requires_allow_write(sqlite_path: str) -> None:
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "query",
            "-c",
            sqlite_path,
            "--sql",
            "update users set name = 'Alicia' where id = 1",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["error"] is True
    assert payload["code"] == "WRITE_REQUIRES_ALLOW_WRITE"
    assert any("--allow-write" in step["cmd"] for step in payload["try_next"])


def test_validation_error_json_sql_file_not_found_uses_structured_error(sqlite_path: str) -> None:
    result = runner.invoke(
        app,
        ["-f", "json", "query", "-c", sqlite_path, "--file", "/nonexistent/path.sql"],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["error"] is True
    assert payload["code"] == "SQL_FILE_NOT_FOUND"


def test_validation_error_json_completion_invalid_shell_uses_structured_error() -> None:
    result = runner.invoke(app, ["-f", "json", "completion", "show", "nushell"])
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["error"] is True
    assert payload["code"] == "SHELL_INVALID"


def test_validation_error_json_profile_mutually_exclusive_options(
    sqlite_path: str,
) -> None:
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "profile",
            "-c",
            sqlite_path,
            "-t",
            "users",
            "--columns",
            "id",
            "--column-set",
            "default",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["error"] is True
    assert payload["code"] == "MUTUALLY_EXCLUSIVE_OPTIONS"


def test_validation_error_json_assert_comparison_conflict(sqlite_path: str) -> None:
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "assert",
            "-c",
            sqlite_path,
            "--sql",
            "select 1",
            "--expect",
            "1",
            "--expect-gt",
            "0",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["error"] is True
    assert payload["code"] == "ASSERT_COMPARISON_CONFLICT"


def test_validation_error_json_snowflake_required_uses_structured_error(sqlite_path: str) -> None:
    result = runner.invoke(
        app,
        ["-f", "json", "snowflake", "lineage", "-c", sqlite_path, "--object", "DB.SCHEMA.TBL"],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["error"] is True
    assert payload["code"] == "SNOWFLAKE_REQUIRED"
    assert any("qdo config list" in step["cmd"] for step in payload["try_next"])


# ---------------------------------------------------------------------------
# Fuzzy-suggestion content contract
# ---------------------------------------------------------------------------
#
# When a typo has a close match, the candidate identifier must appear in the
# output so the user can retry.  We intentionally don't assert on the
# "Did you mean" prose framing — that's covered by the _format_not_found
# unit tests below — only that the right candidate shows up.


@pytest.mark.parametrize(
    ("argv", "expected_candidate"),
    [
        (["inspect", "-t", "usrs"], "users"),
        (["inspect", "-t", "user"], "users"),
        (["dist", "-t", "users", "-C", "emal"], "email"),
        (["dist", "-t", "users", "-C", "nam"], "name"),
    ],
    ids=["table-typo", "table-partial", "column-typo-email", "column-typo-name"],
)
def test_fuzzy_suggestion_surfaces_candidate(
    sqlite_path: str, argv: list[str], expected_candidate: str
) -> None:
    result = runner.invoke(app, [*argv, "-c", sqlite_path])
    assert result.exit_code != 0
    assert expected_candidate in result.output


def test_fuzzy_no_crash_on_gibberish(sqlite_path: str) -> None:
    """Unrelated input produces a clean validation error (no traceback)."""
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "zzzzzzz"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output


# ---------------------------------------------------------------------------
# Invalid identifiers
# ---------------------------------------------------------------------------


def test_invalid_table_name(sqlite_path: str):
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "DROP TABLE; --"])
    assert result.exit_code != 0


def test_invalid_column_name(sqlite_path: str):
    result = runner.invoke(
        app, ["dist", "-c", sqlite_path, "-t", "users", "-C", "col; DROP TABLE"]
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Case-insensitive column matching
# ---------------------------------------------------------------------------


def test_dist_case_insensitive_column(sqlite_path: str):
    """Column name matching should be case-insensitive.

    ``resolve_column()`` normalizes at the CLI boundary regardless of
    dialect, so one fixture is enough to prove the contract (the DuckDB
    variant was dropped 2026-04-17).
    """
    result = runner.invoke(app, ["dist", "-c", sqlite_path, "-t", "users", "-C", "NAME"])
    assert result.exit_code == 0


def test_profile_case_insensitive_column_filter(sqlite_path: str):
    """Profile --columns should be case-insensitive."""
    result = runner.invoke(app, ["profile", "-c", sqlite_path, "-t", "users", "--columns", "NAME"])
    assert result.exit_code == 0
    assert "name" in result.output.lower()


# ---------------------------------------------------------------------------
# Case-insensitive metadata lookups (DuckDB)
# ---------------------------------------------------------------------------


def test_duckdb_get_columns_case_insensitive(duckdb_path: str):
    """DuckDB get_columns should work regardless of table name case."""
    from querido.connectors.duckdb import DuckDBConnector

    with DuckDBConnector(duckdb_path) as conn:
        # Table was created as "users" (lowercase)
        cols_lower = conn.get_columns("users")
        cols_upper = conn.get_columns("USERS")
        cols_mixed = conn.get_columns("Users")

        assert len(cols_lower) > 0
        assert len(cols_upper) == len(cols_lower)
        assert len(cols_mixed) == len(cols_lower)


def test_duckdb_get_table_comment_case_insensitive(tmp_path: Path):
    import duckdb

    db_path = str(tmp_path / "comments.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER)")
    conn.execute("COMMENT ON TABLE users IS 'Test comment'")
    conn.close()

    from querido.connectors.duckdb import DuckDBConnector

    with DuckDBConnector(db_path) as connector:
        assert connector.get_table_comment("users") == "Test comment"
        assert connector.get_table_comment("USERS") == "Test comment"


# The standalone ``test_no_traceback_*`` pair was folded into
# ``test_validation_error_contract`` / ``test_missing_connection_file_contract``
# above — every validation error already asserts ``"Traceback" not in``.


# ---------------------------------------------------------------------------
# _error_code / _classify_error — isinstance-based classification (R.23)
# ---------------------------------------------------------------------------
#
# Replaces the prior string-match classifier. Driver exceptions are wrapped
# into ConnectorError subclasses by each connector's execute()/__init__, and
# the CLI classifier switches on type rather than message text.


@pytest.mark.parametrize(
    ("exc_factory", "expected_code"),
    [
        (lambda: _conn_err("TableNotFoundError", "orders"), "TABLE_NOT_FOUND"),
        (lambda: _conn_err("ColumnNotFoundError", "email", "users"), "COLUMN_NOT_FOUND"),
        (lambda: _conn_err("DatabaseLockedError", "database is locked"), "DATABASE_LOCKED"),
        (lambda: _conn_err("DatabaseOpenError", "unable to open"), "DATABASE_OPEN_FAILED"),
        (lambda: _conn_err("AuthenticationError", "bad password"), "AUTH_FAILED"),
        (lambda: _conn_err("DatabaseError", "syntax error"), "DATABASE_ERROR"),
        (lambda: FileNotFoundError("missing.db"), "FILE_NOT_FOUND"),
        (lambda: ValueError("bad input"), "VALIDATION_ERROR"),
        (lambda: ImportError("no duckdb"), "MISSING_DEPENDENCY"),
        (lambda: PermissionError("denied"), "PERMISSION_DENIED"),
        (lambda: RuntimeError("oops"), "UNKNOWN_ERROR"),
    ],
    ids=[
        "table-not-found",
        "column-not-found",
        "database-locked",
        "database-open",
        "authentication",
        "database-error",
        "file-not-found",
        "value-error",
        "import-error",
        "permission-error",
        "unknown",
    ],
)
def test_error_code_from_typed_exception(exc_factory, expected_code: str):
    from querido.cli._errors import _error_code

    assert _error_code(exc_factory()) == expected_code


def _conn_err(name: str, *args):
    """Construct a :class:`ConnectorError` subclass by name for parametrization."""
    import querido.connectors.base as base

    cls = getattr(base, name)
    return cls(*args)


def test_emit_rich_error_preserves_bracketed_text_in_hints(capsys: pytest.CaptureFixture[str]):
    """Regression: missing-extra hint must render `[duckdb]` / `[snowflake]` literally.

    Rich was interpreting the brackets as markup tags and dropping them, producing
    `uv pip install 'querido' or 'querido'` — a useless install instruction.
    """
    from querido.cli._errors import _emit_rich_error

    try_next = [
        {"cmd": "uv pip install 'querido[duckdb]'", "why": "Install the DuckDB extra."},
        {"cmd": "uv pip install 'querido[snowflake]'", "why": "Install the Snowflake extra."},
    ]
    _emit_rich_error("No module named duckdb", ImportError("duckdb"), None, try_next)

    err = capsys.readouterr().err
    assert "'querido[duckdb]'" in err
    assert "'querido[snowflake]'" in err
    assert "Install the missing extra" in err


# ---------------------------------------------------------------------------
# Unit tests for _format_not_found / _fuzzy_suggestions
# ---------------------------------------------------------------------------


def test_format_not_found_with_close_match():
    from querido.cli._validation import _format_not_found

    msg = _format_not_found("Table", "usrs", ["users", "orders", "products"])
    assert "Did you mean" in msg
    assert "users" in msg
    assert "Available" in msg


def test_format_not_found_large_list_no_available():
    from querido.cli._validation import _format_not_found

    candidates = [f"table_{i}" for i in range(100)]
    msg = _format_not_found("Table", "table_1", candidates, max_available=30)
    assert "Did you mean" in msg
    assert "Available" not in msg


def test_format_not_found_preserves_original_casing():
    from querido.cli._validation import _format_not_found

    msg = _format_not_found("Column", "usr_id", ["USER_ID", "ORDER_ID", "TOTAL"])
    assert "Did you mean" in msg
    assert "USER_ID" in msg


def test_fuzzy_suggestions_returns_matches():
    from querido.cli._validation import _fuzzy_suggestions

    matches = _fuzzy_suggestions("usrs", ["users", "orders", "products"])
    assert "users" in matches


# ---------------------------------------------------------------------------
# resolve_table — case-insensitive table name resolution
# ---------------------------------------------------------------------------


def test_resolve_table_exact_match(sqlite_path: str):
    from querido.cli._validation import resolve_table
    from querido.connectors.sqlite import SQLiteConnector

    with SQLiteConnector(sqlite_path) as conn:
        assert resolve_table(conn, "users") == "users"


def test_resolve_table_case_insensitive(sqlite_path: str):
    """User types USERS, table is users — resolver returns canonical name.

    ``resolve_table()`` delegates to ``connector.get_tables()`` and does the
    case-insensitive match in Python; it's dialect-neutral. The DuckDB
    variant was dropped 2026-04-17.
    """
    from querido.cli._validation import resolve_table
    from querido.connectors.sqlite import SQLiteConnector

    with SQLiteConnector(sqlite_path) as conn:
        assert resolve_table(conn, "USERS") == "users"
        assert resolve_table(conn, "Users") == "users"
        assert resolve_table(conn, "ORDERS") == "orders"


def test_resolve_table_not_found_raises(sqlite_path: str):
    import typer

    from querido.cli._validation import resolve_table
    from querido.connectors.sqlite import SQLiteConnector

    with (
        SQLiteConnector(sqlite_path) as conn,
        pytest.raises(typer.BadParameter, match="not found"),
    ):
        resolve_table(conn, "nonexistent")


def test_resolve_table_not_found_has_suggestions(sqlite_path: str):
    """resolve_table error should include fuzzy suggestions."""
    import typer

    from querido.cli._validation import resolve_table
    from querido.connectors.sqlite import SQLiteConnector

    with (
        SQLiteConnector(sqlite_path) as conn,
        pytest.raises(typer.BadParameter, match="Did you mean"),
    ):
        resolve_table(conn, "usrs")


# ---------------------------------------------------------------------------
# CLI commands accept case-insensitive table names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["preview", "-t", "USERS", "-r", "1"],
        ["inspect", "-t", "USERS"],
        ["sql", "select", "-t", "USERS"],
        ["profile", "-t", "USERS"],
    ],
    ids=["preview", "inspect", "sql-select", "profile"],
)
def test_cli_accepts_case_insensitive_table(sqlite_path: str, argv: list[str]) -> None:
    """Contract: every table-scoped command resolves USERS → users."""
    result = runner.invoke(app, [*argv, "-c", sqlite_path])
    assert result.exit_code == 0


def test_sql_select_case_insensitive_emits_canonical_name(sqlite_path: str) -> None:
    """sql select should output the canonical (lowercase) table name."""
    result = runner.invoke(app, ["sql", "select", "-c", sqlite_path, "-t", "USERS"])
    assert result.exit_code == 0
    assert "from users;" in result.output
