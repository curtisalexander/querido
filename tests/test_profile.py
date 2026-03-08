from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_profile_sqlite(sqlite_path: str):
    result = runner.invoke(app, ["profile", "--connection", sqlite_path, "--table", "users"])
    assert result.exit_code == 0
    assert "Numeric Columns" in result.output


def test_profile_top_values(sqlite_path: str):
    result = runner.invoke(
        app,
        ["profile", "--connection", sqlite_path, "--table", "users", "--top", "3"],
    )
    assert result.exit_code == 0
    assert "Top values" in result.output
    assert "Alice" in result.output
    assert "Bob" in result.output


def test_profile_top_zero_hides_frequencies(sqlite_path: str):
    result = runner.invoke(app, ["profile", "--connection", sqlite_path, "--table", "users"])
    assert result.exit_code == 0
    assert "Top values" not in result.output
