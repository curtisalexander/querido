import json
import os

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_config_add_sqlite(tmp_path):
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    result = runner.invoke(
        app,
        ["config", "add", "--name", "mydb", "--type", "sqlite", "--path", "/tmp/test.db"],
        env=env,
    )
    assert result.exit_code == 0
    assert "Added connection" in result.output

    # Verify the file was written
    config_file = tmp_path / "connections.toml"
    assert config_file.exists()
    content = config_file.read_text()
    assert "[connections.mydb]" in content
    assert 'type = "sqlite"' in content
    assert 'path = "/tmp/test.db"' in content


def test_missing_backend_extra_helper():
    """The extras probe returns None when importable, extras-name otherwise."""
    from querido.cli.config import _missing_backend_extra

    # sqlite is stdlib and never reports missing
    assert _missing_backend_extra("sqlite") is None
    # Unknown type also returns None (we only probe known backends)
    assert _missing_backend_extra("mysql") is None


def test_config_add_warns_when_backend_extra_missing(tmp_path, monkeypatch):
    """Adding a duckdb/snowflake connection without the extra should warn, not fail."""
    from querido.cli import config as config_cli

    monkeypatch.setattr(config_cli, "_missing_backend_extra", lambda db_type: "duckdb")

    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    result = runner.invoke(
        app,
        ["config", "add", "--name", "mydb", "--type", "duckdb", "--path", "/tmp/test.duckdb"],
        env=env,
    )
    assert result.exit_code == 0
    assert "Added connection" in result.output
    # The warning is actionable and points at the exact install command
    assert "the duckdb backend isn't installed" in result.output
    assert "querido[duckdb]" in result.output


def test_config_add_duplicate_rejected(tmp_path):
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    runner.invoke(
        app,
        ["config", "add", "--name", "mydb", "--type", "sqlite", "--path", "/tmp/test.db"],
        env=env,
    )
    result = runner.invoke(
        app,
        ["config", "add", "--name", "mydb", "--type", "sqlite", "--path", "/tmp/other.db"],
        env=env,
    )
    assert result.exit_code != 0


def test_config_add_duplicate_rejected_json(tmp_path):
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    runner.invoke(
        app,
        ["config", "add", "--name", "mydb", "--type", "sqlite", "--path", "/tmp/test.db"],
        env=env,
    )
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "config",
            "add",
            "--name",
            "mydb",
            "--type",
            "sqlite",
            "--path",
            "/tmp/other.db",
        ],
        env=env,
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["code"] == "CONNECTION_EXISTS"


def test_config_add_requires_path_for_sqlite(tmp_path):
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    result = runner.invoke(
        app,
        ["config", "add", "--name", "mydb", "--type", "sqlite"],
        env=env,
    )
    assert result.exit_code != 0


def test_config_list_empty(tmp_path):
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    result = runner.invoke(app, ["config", "list"], env=env)
    assert result.exit_code == 0
    assert "No connections" in result.output


def test_config_list_shows_connections(tmp_path):
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    runner.invoke(
        app,
        ["config", "add", "--name", "testdb", "--type", "duckdb", "--path", "/data/my.duckdb"],
        env=env,
    )
    result = runner.invoke(app, ["config", "list"], env=env)
    assert result.exit_code == 0
    assert "testdb" in result.output
    assert "duckdb" in result.output


def test_config_list_json_uses_structured_envelope(tmp_path):
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    runner.invoke(
        app,
        ["config", "add", "--name", "testdb", "--type", "duckdb", "--path", "/data/my.duckdb"],
        env=env,
    )
    result = runner.invoke(app, ["-f", "json", "config", "list"], env=env)
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["command"] == "config list"
    assert payload["data"]["connections"][0]["name"] == "testdb"
    assert payload["data"]["connections"][0]["path"] == "/data/my.duckdb"


def test_config_list_snowflake_columns(tmp_path):
    """When Snowflake connections exist, list shows dedicated columns for role/warehouse."""
    env = {**os.environ, "QDO_CONFIG": str(tmp_path), "COLUMNS": "200"}
    runner.invoke(
        app,
        [
            "config",
            "add",
            "--name",
            "sf-analytics",
            "--type",
            "snowflake",
            "--account",
            "xy123",
            "--database",
            "ANALYTICS",
            "--schema",
            "PUBLIC",
            "--role",
            "ANALYST",
            "--warehouse",
            "COMPUTE_WH",
        ],
        env=env,
    )
    result = runner.invoke(app, ["config", "list"], env=env)
    assert result.exit_code == 0
    assert "ANALYST" in result.output
    assert "COMPUTE_WH" in result.output
    assert "ANALYTICS" in result.output


# ── config clone ──────────────────────────────────────────────────────


def test_config_remove_basic(tmp_path):
    """Remove with --yes drops the connection and leaves others intact."""
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    runner.invoke(
        app,
        ["config", "add", "--name", "keepme", "--type", "sqlite", "--path", "/tmp/a.db"],
        env=env,
    )
    runner.invoke(
        app,
        ["config", "add", "--name", "gone", "--type", "sqlite", "--path", "/tmp/b.db"],
        env=env,
    )
    result = runner.invoke(app, ["config", "remove", "--name", "gone", "--yes"], env=env)
    assert result.exit_code == 0
    assert "Removed connection" in result.output

    config_file = tmp_path / "connections.toml"
    content = config_file.read_text()
    assert "[connections.keepme]" in content
    assert "[connections.gone]" not in content


def test_config_remove_confirmation_abort(tmp_path):
    """Without --yes, answering 'n' at the prompt aborts without writing."""
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    runner.invoke(
        app,
        ["config", "add", "--name", "mydb", "--type", "sqlite", "--path", "/tmp/a.db"],
        env=env,
    )
    # Feed 'n' to the confirmation prompt
    result = runner.invoke(app, ["config", "remove", "--name", "mydb"], env=env, input="n\n")
    assert result.exit_code == 0
    assert "Aborted" in result.output

    config_file = tmp_path / "connections.toml"
    assert "[connections.mydb]" in config_file.read_text()


def test_config_remove_unknown_name_uses_structured_error(tmp_path):
    """Removing a nonexistent connection raises CONNECTION_NOT_FOUND under -f json."""
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    result = runner.invoke(
        app, ["-f", "json", "config", "remove", "--name", "ghost", "--yes"], env=env
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload.get("error") is True
    assert payload.get("code") == "CONNECTION_NOT_FOUND"


def test_config_clone_basic(tmp_path):
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    runner.invoke(
        app,
        [
            "config",
            "add",
            "--name",
            "prod",
            "--type",
            "snowflake",
            "--account",
            "xy123",
            "--database",
            "PROD",
            "--schema",
            "PUBLIC",
            "--role",
            "PROD_ROLE",
            "--warehouse",
            "PROD_WH",
        ],
        env=env,
    )
    result = runner.invoke(
        app,
        [
            "config",
            "clone",
            "--source",
            "prod",
            "--name",
            "finance",
            "--database",
            "FINANCE_DB",
            "--role",
            "FINANCE_ROLE",
        ],
        env=env,
    )
    assert result.exit_code == 0
    assert "Cloned" in result.output

    # Verify the cloned connection in the file
    content = (tmp_path / "connections.toml").read_text()
    assert "[connections.finance]" in content
    assert 'database = "FINANCE_DB"' in content
    assert 'role = "FINANCE_ROLE"' in content
    # Non-overridden fields should carry over
    assert content.count('account = "xy123"') == 2  # both prod and finance


def test_config_clone_missing_source(tmp_path):
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    result = runner.invoke(
        app,
        ["config", "clone", "--source", "nonexistent", "--name", "new"],
        env=env,
    )
    assert result.exit_code != 0


def test_config_clone_missing_source_json(tmp_path):
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    result = runner.invoke(
        app,
        ["-f", "json", "config", "clone", "--source", "nonexistent", "--name", "new"],
        env=env,
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["code"] == "CONNECTION_NOT_FOUND"
    assert any("qdo config list" in step["cmd"] for step in payload["try_next"])


def test_config_clone_duplicate_name(tmp_path):
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    runner.invoke(
        app,
        [
            "config",
            "add",
            "--name",
            "prod",
            "--type",
            "snowflake",
            "--account",
            "xy123",
            "--database",
            "PROD",
        ],
        env=env,
    )
    result = runner.invoke(
        app,
        ["config", "clone", "--source", "prod", "--name", "prod"],
        env=env,
    )
    assert result.exit_code != 0


def test_config_clone_no_overrides(tmp_path):
    """Cloning without overrides creates an exact copy."""
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    runner.invoke(
        app,
        [
            "config",
            "add",
            "--name",
            "orig",
            "--type",
            "snowflake",
            "--account",
            "xy123",
            "--database",
            "DB1",
            "--role",
            "R1",
        ],
        env=env,
    )
    result = runner.invoke(
        app,
        ["config", "clone", "--source", "orig", "--name", "copy"],
        env=env,
    )
    assert result.exit_code == 0
    content = (tmp_path / "connections.toml").read_text()
    assert "[connections.copy]" in content


# ---------------------------------------------------------------------------
# config test
# ---------------------------------------------------------------------------


def test_config_test_sqlite(sqlite_path):
    result = runner.invoke(app, ["config", "test", sqlite_path])
    assert result.exit_code == 0
    assert "OK" in result.output
    assert "sqlite" in result.output


def test_config_test_duckdb(duckdb_path):
    result = runner.invoke(app, ["config", "test", duckdb_path])
    assert result.exit_code == 0
    assert "OK" in result.output
    assert "duckdb" in result.output


def test_config_test_named_connection(tmp_path, sqlite_path):
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    # Add a named connection pointing to a real database
    runner.invoke(
        app,
        ["config", "add", "--name", "mydb", "--type", "sqlite", "--path", sqlite_path],
        env=env,
    )
    result = runner.invoke(app, ["config", "test", "mydb"], env=env)
    assert result.exit_code == 0
    assert "OK" in result.output


def test_config_test_missing_file():
    result = runner.invoke(app, ["config", "test", "/nonexistent/path.db"])
    assert result.exit_code != 0


def test_config_test_invalid_connection(tmp_path):
    env = {**os.environ, "QDO_CONFIG": str(tmp_path)}
    result = runner.invoke(app, ["config", "test", "no_such_connection"], env=env)
    assert result.exit_code != 0
