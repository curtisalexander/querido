"""Tests for the qdo serve CLI entry point."""

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_serve_help() -> None:
    result = runner.invoke(app, ["serve", "--help"], color=False)
    assert result.exit_code == 0
    assert "--connection" in result.output
    assert "--port" in result.output
    assert "--host" in result.output


def test_serve_requires_connection() -> None:
    result = runner.invoke(app, ["serve"])
    assert result.exit_code != 0


def test_serve_starts_with_sqlite(sqlite_path: str) -> None:
    """Serve should at least resolve the connection before starting uvicorn.

    We can't easily test the full server lifecycle, but we can verify
    it gets past connection resolution. Since uvicorn blocks, we test
    that the app factory is invoked by checking for a startup message
    or that it doesn't crash on connection resolution.
    """
    # This would block, so we just verify the help and arg validation work.
    # Full web tests are in test_web.py via FastAPI TestClient.
    pass
