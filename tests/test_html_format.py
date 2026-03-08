"""Tests for --format html on all commands that support it."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def _invoke_html(args: list[str]) -> tuple[int, str]:
    """Run a CLI command with --format html, mocking webbrowser.open.

    Returns (exit_code, html_file_contents).
    """
    written_path: list[str] = []

    def fake_open(uri: str) -> None:
        # uri is a file:// URL; extract the path
        if uri.startswith("file://"):
            written_path.append(uri.removeprefix("file://"))
        else:
            written_path.append(uri)

    with patch("webbrowser.open", side_effect=fake_open):
        result = runner.invoke(app, ["--format", "html", *args])

    if result.exit_code != 0:
        return result.exit_code, result.output

    assert written_path, f"No HTML file was opened. stdout={result.output}"
    html_content = Path(written_path[0]).read_text()

    # Clean up temp file
    Path(written_path[0]).unlink(missing_ok=True)

    return result.exit_code, html_content


# -- inspect -------------------------------------------------------------------


def test_inspect_html(sqlite_path: str) -> None:
    code, html = _invoke_html(["inspect", "-c", sqlite_path, "-t", "users"])
    assert code == 0
    assert "<!DOCTYPE html>" in html
    assert "Inspect: users" in html
    assert "<table>" in html
    assert "Alice" not in html  # inspect shows metadata, not data


def test_inspect_html_has_interactive_js(sqlite_path: str) -> None:
    code, html = _invoke_html(["inspect", "-c", sqlite_path, "-t", "users"])
    assert code == 0
    assert "copyTable" in html
    assert "exportCSV" in html
    assert "filter-input" in html


# -- preview -------------------------------------------------------------------


def test_preview_html(sqlite_path: str) -> None:
    code, html = _invoke_html(["preview", "-c", sqlite_path, "-t", "users"])
    assert code == 0
    assert "Preview: users" in html
    assert "Alice" in html
    assert "Bob" in html


def test_preview_html_has_sort(sqlite_path: str) -> None:
    code, html = _invoke_html(["preview", "-c", sqlite_path, "-t", "users"])
    assert code == 0
    assert "sort-arrow" in html
    assert "doSort" in html


# -- profile -------------------------------------------------------------------


def test_profile_html(sqlite_path: str) -> None:
    code, html = _invoke_html(["profile", "-c", sqlite_path, "-t", "users"])
    assert code == 0
    assert "Profile: users" in html
    assert "<table>" in html


# -- search --------------------------------------------------------------------


def test_search_html(sqlite_path: str) -> None:
    code, html = _invoke_html(["search", "-c", sqlite_path, "-p", "user"])
    assert code == 0
    assert "Search:" in html
    assert "users" in html


# -- dist ----------------------------------------------------------------------


def test_dist_html(sqlite_path: str) -> None:
    code, html = _invoke_html(["dist", "-c", sqlite_path, "-t", "users", "-col", "age"])
    assert code == 0
    assert "Distribution:" in html
    assert "age" in html


# -- template ------------------------------------------------------------------


def test_template_html(sqlite_path: str) -> None:
    code, html = _invoke_html(["template", "-c", sqlite_path, "-t", "users"])
    assert code == 0
    assert "Template: users" in html
    assert "<table>" in html


# -- html validation -----------------------------------------------------------


def test_html_has_dark_mode_support(sqlite_path: str) -> None:
    """HTML output should support dark mode via prefers-color-scheme."""
    code, html = _invoke_html(["preview", "-c", sqlite_path, "-t", "users"])
    assert code == 0
    assert "prefers-color-scheme: dark" in html


def test_html_has_export_buttons(sqlite_path: str) -> None:
    """HTML output should have Copy and Export CSV buttons."""
    code, html = _invoke_html(["preview", "-c", sqlite_path, "-t", "users"])
    assert code == 0
    assert "Copy" in html
    assert "Export CSV" in html
