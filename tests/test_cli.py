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


def test_completion_bash():
    result = runner.invoke(app, ["completion", "show", "bash"])
    assert result.exit_code == 0
    assert "_qdo_completion" in result.output or "_QDO_COMPLETE" in result.output


def test_completion_zsh():
    result = runner.invoke(app, ["completion", "show", "zsh"])
    assert result.exit_code == 0
    assert "_QDO_COMPLETE" in result.output


def test_completion_fish():
    result = runner.invoke(app, ["completion", "show", "fish"])
    assert result.exit_code == 0
    assert "complete" in result.output


def test_completion_powershell():
    result = runner.invoke(app, ["completion", "show", "powershell"])
    assert result.exit_code == 0
    assert "_QDO_COMPLETE" in result.output


def test_completion_invalid_shell():
    result = runner.invoke(app, ["completion", "show", "csh"])
    assert result.exit_code != 0


def test_completion_hint():
    result = runner.invoke(app, ["completion", "show", "bash", "--hint"])
    assert result.exit_code == 0
    assert "bashrc" in result.output
