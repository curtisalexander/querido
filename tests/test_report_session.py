"""Tests for ``qdo report session`` and ``qdo session note``.

Phase 6.1 acceptance criterion from PLAN.md: "run a 5-step session,
export to HTML, email to someone without qdo installed, they can read it
in a browser offline." Encoded here as the end-to-end test that builds a
real 5-step session via the CLI, exports to HTML, and asserts the
offline-readable invariants (no external JS, no blocking image fetches,
self-contained CSS).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from querido.cli.main import app
from querido.core.report import build_session_report
from querido.core.session import SESSIONS_ROOT, STEPS_FILE, session_dir
from querido.output.report_html import render_session_report

runner = CliRunner()


def _run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> Result:
    """Invoke the CLI from *cwd* with optional env overrides."""
    env_full = {**os.environ, **(env or {})}
    old_cwd = Path.cwd()
    try:
        os.chdir(cwd)
        return runner.invoke(app, args, env=env_full)
    finally:
        os.chdir(old_cwd)


def _seed_step(
    cwd: Path,
    name: str,
    *,
    index: int,
    cmd: str,
    args: list[str],
    stdout: str,
    exit_code: int = 0,
    row_count: int | None = None,
    duration: float = 0.1,
    note: str | None = None,
) -> dict:
    """Write one step's record + stdout file under *cwd*/.qdo/sessions/<name>/."""
    dir_ = session_dir(name, cwd=cwd)
    dir_.mkdir(parents=True, exist_ok=True)
    step_dir = dir_ / f"step_{index}"
    step_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = step_dir / "stdout"
    stdout_path.write_text(stdout, encoding="utf-8")

    record = {
        "index": index,
        "timestamp": "2026-04-20T00:00:00+00:00",
        "cmd": cmd,
        "args": args,
        "duration": duration,
        "exit_code": exit_code,
        "row_count": row_count,
        "stdout_path": str(stdout_path.relative_to(cwd / ".qdo")),
    }
    if note is not None:
        record["note"] = note

    with (dir_ / STEPS_FILE).open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record


# ---------------------------------------------------------------------------
# build_session_report
# ---------------------------------------------------------------------------


def test_build_session_report_loads_records_and_stdout(tmp_path: Path) -> None:
    _seed_step(
        tmp_path,
        "s1",
        index=1,
        cmd="qdo catalog",
        args=["catalog", "-c", "mydb"],
        stdout='{"command": "catalog", "data": {}}',
        row_count=3,
    )
    _seed_step(
        tmp_path,
        "s1",
        index=2,
        cmd="qdo profile",
        args=["profile", "-c", "mydb", "-t", "t"],
        stdout="profile output",
        row_count=100,
    )

    report = build_session_report("s1", cwd=tmp_path)

    assert report["session_name"] == "s1"
    assert report["step_count"] == 2
    assert [s["index"] for s in report["steps"]] == [1, 2]
    assert report["steps"][0]["stdout"].startswith('{"command"')
    assert report["steps"][1]["stdout"] == "profile output"
    assert report["steps"][1]["cmd"] == "qdo profile"
    assert report["generated_at"]  # ISO timestamp is filled in


def test_build_session_report_missing_session_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_session_report("nope", cwd=tmp_path)


def test_build_session_report_tolerates_missing_stdout_file(tmp_path: Path) -> None:
    """If a stdout file was deleted, the step still renders (empty output)."""
    _seed_step(tmp_path, "s1", index=1, cmd="qdo catalog", args=["catalog"], stdout="x")
    # Delete the stdout file manually to simulate disk corruption / cleanup.
    (tmp_path / SESSIONS_ROOT / "s1" / "step_1" / "stdout").unlink()

    report = build_session_report("s1", cwd=tmp_path)
    assert report["step_count"] == 1
    assert report["steps"][0]["stdout"] == ""


def test_build_session_report_preserves_notes(tmp_path: Path) -> None:
    _seed_step(
        tmp_path,
        "s1",
        index=1,
        cmd="qdo profile",
        args=["profile"],
        stdout="out",
        note="follow up on amount nulls",
    )
    report = build_session_report("s1", cwd=tmp_path)
    assert report["steps"][0]["note"] == "follow up on amount nulls"


# ---------------------------------------------------------------------------
# render_session_report
# ---------------------------------------------------------------------------


def _minimal_report(**overrides) -> dict:
    base = {
        "session_name": "demo",
        "generated_at": "2026-04-20T00:00:00+00:00",
        "step_count": 0,
        "steps": [],
        "command": "",
    }
    base.update(overrides)
    return base


def test_render_has_page_shell_and_title() -> None:
    html = render_session_report(_minimal_report())
    assert html.startswith("<!DOCTYPE html>")
    assert "<title>demo — qdo session report</title>" in html
    assert "<h1>demo</h1>" in html


def test_render_empty_session_still_has_header_and_footer() -> None:
    html = render_session_report(_minimal_report())
    assert "qdo report · session" in html
    assert '<span class="k">steps</span><span class="v">0</span>' in html
    assert "Generated with qdo" in html


def test_render_includes_card_per_step() -> None:
    report = _minimal_report(
        step_count=2,
        steps=[
            {
                "index": 1,
                "cmd": "qdo catalog",
                "args": ["catalog", "-c", "mydb"],
                "duration": 0.42,
                "exit_code": 0,
                "row_count": 3,
                "timestamp": "2026-04-20T00:00:00+00:00",
                "stdout": "tables: customers, orders",
            },
            {
                "index": 2,
                "cmd": "qdo quality",
                "args": ["quality", "-c", "mydb", "-t", "orders"],
                "duration": 1.3,
                "exit_code": 0,
                "row_count": None,
                "timestamp": "2026-04-20T00:00:01+00:00",
                "stdout": "quality output",
            },
        ],
    )
    html = render_session_report(report)
    assert html.count('class="panel step') == 2
    assert "#1" in html
    assert "#2" in html
    # Alternates the theme class between cards
    assert "theme-indigo" in html
    assert "theme-violet" in html


def test_render_failed_step_marks_exit_and_opens_details() -> None:
    report = _minimal_report(
        step_count=1,
        steps=[
            {
                "index": 1,
                "cmd": "qdo query",
                "args": ["query", "--sql", "select 1"],
                "duration": 0.1,
                "exit_code": 2,
                "row_count": None,
                "timestamp": "2026-04-20T00:00:00+00:00",
                "stdout": "boom",
            }
        ],
    )
    html = render_session_report(report)
    assert '<span class="pill fail">exit 2</span>' in html
    # Details block opens by default on failure so readers see the failure
    # without having to click.
    assert "<details" in html and "open" in html
    # Header should surface the failure count.
    assert '<span class="k">failures</span><span class="v">1</span>' in html


def test_render_escapes_html_unsafe_content() -> None:
    """Stdout and note content is untrusted — must be HTML-escaped."""
    report = _minimal_report(
        step_count=1,
        steps=[
            {
                "index": 1,
                "cmd": "qdo query",
                "args": ["query"],
                "duration": 0.1,
                "exit_code": 0,
                "timestamp": "ts",
                "stdout": "<script>alert('xss')</script>",
                "note": "<img src=x onerror=alert(1)>",
            }
        ],
    )
    html = render_session_report(report)
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert" in html
    assert "<img src=x" not in html
    assert "&lt;img src=x" in html


def test_render_pretty_prints_json_stdout() -> None:
    report = _minimal_report(
        step_count=1,
        steps=[
            {
                "index": 1,
                "cmd": "qdo catalog",
                "args": ["catalog"],
                "duration": 0.1,
                "exit_code": 0,
                "timestamp": "ts",
                "stdout": '{"command":"catalog","data":{"tables":[]}}',
            }
        ],
    )
    html = render_session_report(report)
    # Indented (2-space) JSON — the raw string was all on one line.
    assert "  &quot;command&quot;: &quot;catalog&quot;" in html


def test_render_note_appears_as_commentary() -> None:
    report = _minimal_report(
        step_count=1,
        steps=[
            {
                "index": 1,
                "cmd": "qdo profile",
                "args": ["profile"],
                "duration": 0.1,
                "exit_code": 0,
                "timestamp": "ts",
                "stdout": "",
                "note": "amount has 2.7% nulls",
            }
        ],
    )
    html = render_session_report(report)
    assert '<div class="step-note">amount has 2.7% nulls</div>' in html


def test_render_no_javascript_anywhere() -> None:
    """Single-file HTML — no scripts, no external JS, no event handlers.

    Also rejects any ``<script>`` tag, ``<iframe>``, or ``on*=`` handler
    that would let the report misbehave offline or leak data on open.
    """
    report = _minimal_report(
        step_count=1,
        steps=[
            {
                "index": 1,
                "cmd": "qdo catalog",
                "args": ["catalog"],
                "duration": 0.1,
                "exit_code": 0,
                "timestamp": "ts",
                "stdout": "ok",
            }
        ],
    )
    html = render_session_report(report)
    assert "<script" not in html
    assert "<iframe" not in html
    # Crude heuristic: no DOM event handlers in attributes.
    import re

    assert re.search(r"\son\w+\s*=", html) is None


# ---------------------------------------------------------------------------
# qdo session note
# ---------------------------------------------------------------------------


def test_session_note_annotates_last_step(tmp_path: Path) -> None:
    _seed_step(tmp_path, "s1", index=1, cmd="qdo catalog", args=["catalog"], stdout="x")
    _seed_step(tmp_path, "s1", index=2, cmd="qdo profile", args=["profile"], stdout="y")

    result = _run(
        ["session", "note", "check this column", "-s", "s1"],
        cwd=tmp_path,
    )
    assert result.exit_code == 0, result.output
    assert "Annotated step 2" in result.output

    steps_file = tmp_path / SESSIONS_ROOT / "s1" / STEPS_FILE
    lines = [json.loads(line) for line in steps_file.read_text().splitlines() if line]
    assert lines[0].get("note") is None
    assert lines[1]["note"] == "check this column"


def test_session_note_uses_env_var_session(tmp_path: Path) -> None:
    _seed_step(tmp_path, "envsess", index=1, cmd="qdo catalog", args=["catalog"], stdout="x")
    result = _run(
        ["session", "note", "hello"],
        cwd=tmp_path,
        env={"QDO_SESSION": "envsess"},
    )
    assert result.exit_code == 0, result.output

    steps_file = tmp_path / SESSIONS_ROOT / "envsess" / STEPS_FILE
    last = json.loads(steps_file.read_text().splitlines()[-1])
    assert last["note"] == "hello"


def test_session_note_requires_session(tmp_path: Path) -> None:
    """No QDO_SESSION and no -s: clear error, not a crash."""
    result = _run(
        ["session", "note", "orphan"],
        cwd=tmp_path,
        env={"QDO_SESSION": ""},
    )
    assert result.exit_code != 0
    assert "QDO_SESSION" in result.output or "--session" in result.output


def test_session_note_errors_on_empty_session(tmp_path: Path) -> None:
    (tmp_path / SESSIONS_ROOT / "blank").mkdir(parents=True)
    result = _run(
        ["session", "note", "nothing to annotate", "-s", "blank"],
        cwd=tmp_path,
    )
    assert result.exit_code != 0
    assert "no steps" in result.output.lower()


# ---------------------------------------------------------------------------
# qdo report session — acceptance
# ---------------------------------------------------------------------------


def test_report_session_writes_offline_readable_html(tmp_path: Path) -> None:
    """Acceptance: 5-step session → HTML file → opens offline.

    Mirrors PLAN.md 6.1's acceptance criterion. ``offline-readable`` is
    operationalized as: no JavaScript, no blocking <img>/<iframe> fetches,
    CSS is inlined in <style>, page opens as a static file.
    """
    for i, (cmd, args, out) in enumerate(
        [
            ("qdo catalog", ["catalog", "-c", "mydb"], "tables: t1, t2"),
            ("qdo context", ["context", "-c", "mydb", "-t", "t1"], "{}"),
            ("qdo profile", ["profile", "-c", "mydb", "-t", "t1"], "profile ok"),
            ("qdo values", ["values", "-c", "mydb", "-t", "t1", "-C", "c"], "values"),
            ("qdo quality", ["quality", "-c", "mydb", "-t", "t1"], "quality ok"),
        ],
        start=1,
    ):
        _seed_step(tmp_path, "live", index=i, cmd=cmd, args=args, stdout=out, row_count=i)

    out_path = tmp_path / "report.html"
    result = _run(
        ["report", "session", "live", "-o", str(out_path)],
        cwd=tmp_path,
    )
    assert result.exit_code == 0, result.output
    assert out_path.is_file()

    html = out_path.read_text(encoding="utf-8")
    # Page shell
    assert html.startswith("<!DOCTYPE html>")
    assert "<title>live — qdo session report</title>" in html
    # Five cards — one per step, with their commands visible
    assert html.count('class="panel step') == 5
    for cmd in ("qdo catalog", "qdo context", "qdo profile", "qdo values", "qdo quality"):
        assert cmd in html

    # Offline-readable invariants
    assert "<script" not in html
    assert "<iframe" not in html
    # No <img src="http..."> (bad: blocks on network). Inline SVG is fine.
    import re

    assert re.search(r'<img\s[^>]*src\s*=\s*["\']https?://', html) is None
    # CSS lives in a <style> tag, not an external stylesheet.
    assert "<style>" in html
    assert re.search(r'<link\s+[^>]*rel\s*=\s*["\']stylesheet', html) is None


def test_report_session_nonexistent_errors_cleanly(tmp_path: Path) -> None:
    out_path = tmp_path / "report.html"
    result = _run(
        ["report", "session", "missing", "-o", str(out_path)],
        cwd=tmp_path,
    )
    assert result.exit_code != 0
    assert "Session not found" in result.output
    assert not out_path.exists()


def test_report_session_renders_notes_added_via_cli(tmp_path: Path) -> None:
    """The --note → render pipeline works end-to-end."""
    _seed_step(tmp_path, "annotated", index=1, cmd="qdo profile", args=["profile"], stdout="out")
    _run(["session", "note", "watch the amount column", "-s", "annotated"], cwd=tmp_path)

    out_path = tmp_path / "report.html"
    result = _run(
        ["report", "session", "annotated", "-o", str(out_path)],
        cwd=tmp_path,
    )
    assert result.exit_code == 0, result.output
    html = out_path.read_text(encoding="utf-8")
    assert "watch the amount column" in html
    assert 'class="step-note"' in html
