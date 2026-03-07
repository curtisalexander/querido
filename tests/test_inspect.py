from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_inspect_sqlite(sqlite_path: str):
    result = runner.invoke(app, ["inspect", "--connection", sqlite_path, "--table", "users"])
    assert result.exit_code == 0
    assert "id" in result.output
    assert "name" in result.output
    assert "age" in result.output


def test_inspect_duckdb(duckdb_path: str):
    result = runner.invoke(app, ["inspect", "--connection", duckdb_path, "--table", "users"])
    assert result.exit_code == 0
    assert "id" in result.output
    assert "name" in result.output
    assert "age" in result.output


def test_inspect_shows_row_count(sqlite_path: str):
    result = runner.invoke(app, ["inspect", "--connection", sqlite_path, "--table", "users"])
    assert result.exit_code == 0
    assert "2" in result.output
