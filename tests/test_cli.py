from typer.testing import CliRunner

from querido import __version__
from querido.cli.main import app

runner = CliRunner()


def test_root_help_preserves_progressive_discovery_contract():
    """Root help must promote the core before optional and experimental surfaces."""
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert result.output.index("Start Here Commands") < result.output.index(
        "Investigate Deeper Commands"
    )
    for command in ("catalog", "context", "metadata", "query"):
        assert command in result.output
    assert "Experimental declarative workflow runner" in result.output
    assert "requires querido[snowflake]" in result.output
    assert "catalog -c ./data.db" in result.output
    assert "agent install skill" in result.output
    assert "provider-neutral coding-agent" in result.output


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_flags_without_subcommand_exits_nonzero():
    # --show-sql with no subcommand must not silently exit 0; it shows help
    # and exits non-zero like no_args_is_help (L20).
    result = runner.invoke(app, ["--show-sql"])
    assert result.exit_code != 0
    assert "Usage" in result.output


def test_no_subcommand_does_not_break_version():
    # --version is eager and must still exit 0 even though it has no subcommand.
    result = runner.invoke(app, ["--show-sql", "--version"])
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
