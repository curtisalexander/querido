import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_values_sqlite(sqlite_path: str):
    result = runner.invoke(app, ["values", "-c", sqlite_path, "-t", "users", "-C", "name"])
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Bob" in result.output


def test_values_duckdb(duckdb_path: str):
    result = runner.invoke(app, ["values", "-c", duckdb_path, "-t", "users", "-C", "name"])
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Bob" in result.output


def test_values_format_json(sqlite_path: str):
    result = runner.invoke(
        app, ["-f", "json", "values", "-c", sqlite_path, "-t", "users", "-C", "name"]
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    assert payload["column"] == "name"
    assert payload["distinct_count"] == 2
    assert payload["truncated"] is False
    vals = [v["value"] for v in payload["values"]]
    assert "Alice" in vals
    assert "Bob" in vals


def test_values_format_csv(sqlite_path: str):
    result = runner.invoke(
        app, ["-f", "csv", "values", "-c", sqlite_path, "-t", "users", "-C", "name"]
    )
    assert result.exit_code == 0
    assert "value,count" in result.output
    assert "Alice" in result.output


def test_values_format_markdown(sqlite_path: str):
    result = runner.invoke(
        app,
        ["-f", "markdown", "values", "-c", sqlite_path, "-t", "users", "-C", "name"],
    )
    assert result.exit_code == 0
    assert "| Value" in result.output
    assert "Alice" in result.output


def test_values_sort_frequency(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "values",
            "-c",
            sqlite_path,
            "-t",
            "users",
            "-C",
            "name",
            "--sort",
            "frequency",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    # Both have count 1, so order doesn't matter much
    assert len(payload["values"]) == 2


def test_values_truncated(tmp_path: Path):
    """When distinct count exceeds --max, result should be truncated."""
    db_path = str(tmp_path / "many.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, label TEXT)")
    for i in range(50):
        conn.execute("INSERT INTO items VALUES (?, ?)", (i, f"item_{i:03d}"))
    conn.commit()
    conn.close()

    result = runner.invoke(
        app,
        ["-f", "json", "values", "-c", db_path, "-t", "items", "-C", "label", "--max", "10"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    assert payload["distinct_count"] == 50
    assert payload["truncated"] is True
    assert len(payload["values"]) == 10


def test_values_with_nulls(tmp_path: Path):
    db_path = str(tmp_path / "nulls.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER, status TEXT)")
    conn.execute("INSERT INTO t VALUES (1, 'active')")
    conn.execute("INSERT INTO t VALUES (2, NULL)")
    conn.execute("INSERT INTO t VALUES (3, 'inactive')")
    conn.execute("INSERT INTO t VALUES (4, NULL)")
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["-f", "json", "values", "-c", db_path, "-t", "t", "-C", "status"])
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    assert payload["null_count"] == 2
    assert payload["distinct_count"] == 2
    # Values should not include NULLs (they're counted separately)
    vals = [v["value"] for v in payload["values"]]
    assert None not in vals
    assert "active" in vals
    assert "inactive" in vals


def test_values_nonexistent_column(sqlite_path: str):
    result = runner.invoke(app, ["values", "-c", sqlite_path, "-t", "users", "-C", "nonexistent"])
    assert result.exit_code != 0


def test_values_invalid_sort(sqlite_path: str):
    result = runner.invoke(
        app,
        ["values", "-c", sqlite_path, "-t", "users", "-C", "name", "--sort", "bad"],
    )
    assert result.exit_code != 0


def test_values_numeric_column(sqlite_path: str):
    """Works with numeric columns too."""
    result = runner.invoke(
        app, ["-f", "json", "values", "-c", sqlite_path, "-t", "users", "-C", "age"]
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    vals = [v["value"] for v in payload["values"]]
    assert 25 in vals
    assert 30 in vals


def test_values_long_flag_works(sqlite_path: str):
    """``--columns`` (long form) is the canonical name post-R.8."""
    result = runner.invoke(app, ["values", "-c", sqlite_path, "-t", "users", "--columns", "name"])
    assert result.exit_code == 0


def test_values_rejects_multi_column_list(sqlite_path: str):
    """``qdo values`` targets one column; a CSV of length > 1 is a clear error."""
    result = runner.invoke(
        app, ["values", "-c", sqlite_path, "-t", "users", "--columns", "name,age"]
    )
    assert result.exit_code != 0
    assert "exactly one column" in result.output


def test_print_values_rich_summary() -> None:
    """Rich values output should summarize shown/distinct/null counts before the detail table."""
    from rich.console import Console

    from querido.output.console import print_values

    console = Console(record=True, width=120)
    print_values(
        {
            "table": "users",
            "column": "status",
            "values": [{"value": "active", "count": 10}, {"value": "inactive", "count": 3}],
            "distinct_count": 5,
            "null_count": 2,
            "truncated": True,
        },
        console=console,
    )
    text = console.export_text()
    assert "Values Summary" in text
    assert "2 shown" in text
    assert "5 distinct" in text
    assert "2 nulls" in text
    assert "truncated" in text.lower()
    assert "Value Detail" in text


def test_column_singular_alias_accepted(sqlite_path: str):
    """Regression: agents hallucinate `--column` (singular) across values/dist/
    profile. The real flag was `--columns/-C` — we now accept `--column` as
    an alias so a first-call typo doesn't burn a retry.

    Failure mode: in the 2026-04-23 eval run, haiku/sonnet/opus each tried
    ``--column`` on one of these commands, saw a click usage error, retried
    with ``--columns``, and got flagged for a bad-argv path error even though
    the retry succeeded.
    """
    for subcommand in ("values", "dist", "profile"):
        result = runner.invoke(
            app, [subcommand, "-c", sqlite_path, "-t", "users", "--column", "name"]
        )
        assert result.exit_code == 0, (
            f"qdo {subcommand} --column (singular alias) should succeed; got "
            f"exit {result.exit_code}: {result.output[:200]}"
        )
