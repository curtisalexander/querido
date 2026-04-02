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
