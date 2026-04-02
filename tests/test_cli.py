from typer.testing import CliRunner

from querido import __version__
from querido.cli.main import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "qdo" in result.output


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_show_sql_flag(sqlite_path: str):
    result = runner.invoke(
        app, ["--show-sql", "preview", "-c", sqlite_path, "-t", "users", "--rows", "1"]
    )
    assert result.exit_code == 0
    assert "select" in result.output
    assert "limit" in result.output
