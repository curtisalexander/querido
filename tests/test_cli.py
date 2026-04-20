from typer.testing import CliRunner

from querido import __version__
from querido.cli.main import app

runner = CliRunner()


# test_help dropped (2026-04-17): asserted that --help renders and "qdo"
# appears in the output — pure Typer-framework behavior, not our code.


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


def test_debug_flag(sqlite_path: str):
    result = runner.invoke(
        app, ["--debug", "preview", "-c", sqlite_path, "-t", "users", "--rows", "1"]
    )
    assert result.exit_code == 0
    assert "[qdo]" in result.output
    assert "Connection:" in result.output
    assert "Connected" in result.output


def test_no_debug_by_default(sqlite_path: str):
    result = runner.invoke(app, ["preview", "-c", sqlite_path, "-t", "users", "--rows", "1"])
    assert result.exit_code == 0
    assert "[qdo]" not in result.output


# completion tests live in test_completion.py (parametrized across shells).
