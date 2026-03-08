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
