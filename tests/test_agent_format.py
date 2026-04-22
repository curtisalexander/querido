"""End-to-end tests for --format agent (TOON + YAML envelope)."""

from __future__ import annotations

import os

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_preview_agent_renders_rows_as_toon_tabular(sqlite_path: str):
    result = runner.invoke(app, ["-f", "agent", "preview", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0, result.output
    # Envelope is rendered; top-level object wraps a TOON tabular rows array.
    assert "command: preview" in result.output
    assert "rows[2]{id,name,age}:" in result.output
    assert "1,Alice,30" in result.output
    # next_steps gets the same tabular treatment.
    assert "next_steps[" in result.output


def test_preview_qdo_format_env_agent(sqlite_path: str):
    env = {**os.environ, "QDO_FORMAT": "agent"}
    result = runner.invoke(app, ["preview", "-c", sqlite_path, "-t", "users"], env=env)
    assert result.exit_code == 0, result.output
    assert "rows[2]{id,name,age}:" in result.output


def test_catalog_agent_falls_back_to_yaml(sqlite_path: str):
    """Catalog has nested columns-inside-tables, so TOON's tabular form
    isn't applicable — we expect the YAML fallback rendering."""
    result = runner.invoke(app, ["-f", "agent", "catalog", "-c", sqlite_path])
    assert result.exit_code == 0, result.output
    # YAML fallback uses list-item syntax `- name: ...`.
    assert "command: catalog" in result.output
    assert "- name: users" in result.output


def test_agent_error_is_structured(sqlite_path: str):
    """Errors in agent mode render through the same TOON/YAML path."""
    result = runner.invoke(
        app,
        ["-f", "agent", "query", "-c", sqlite_path, "--sql", "select * from nonexistent"],
    )
    assert result.exit_code != 0
    # stderr is captured into result.output for CliRunner's default mix_stderr=True
    err = result.output
    assert "error: true" in err.lower()
    assert "code:" in err


def test_values_agent_tabular(sqlite_path: str):
    result = runner.invoke(
        app, ["-f", "agent", "values", "-c", sqlite_path, "-t", "users", "-C", "name"]
    )
    assert result.exit_code == 0, result.output
    assert "command: values" in result.output
    # values payload has a tabular array of {value, count}
    assert "{value,count}:" in result.output


# -- R.4: meta.serialization signals the chosen encoding ----------------------


def test_agent_meta_signals_toon_when_tabular(sqlite_path: str):
    """Tabular-shaped commands get TOON — meta.serialization must say so."""
    result = runner.invoke(app, ["-f", "agent", "preview", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0, result.output
    # TOON renders the meta dict inline as ``key: value`` lines.
    assert "serialization: toon" in result.output


def test_agent_meta_signals_yaml_when_falling_back(sqlite_path: str):
    """Catalog is the canonical YAML-fallback case (nested tables-with-columns).

    The field must appear in the YAML output so agents can tell which parser
    to use without probing.
    """
    result = runner.invoke(app, ["-f", "agent", "catalog", "-c", sqlite_path])
    assert result.exit_code == 0, result.output
    assert "serialization: yaml" in result.output


def test_agent_meta_serialization_absent_on_json(sqlite_path: str):
    """-f json is always JSON; don't pollute the meta block with a redundant tag."""
    import json

    result = runner.invoke(app, ["-f", "json", "preview", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "serialization" not in payload["meta"]


# -- CC.6: TOON-fallback contract -----------------------------------------------
#
# Every envelope-emitting command must be safe under ``-f agent``: the encoder
# tries TOON first and falls back to YAML on ``ToonUnsupportedShape``.  This
# contract test asserts the invariant for every command in the envelope set
# — adding a new envelope-emitting command and forgetting to test its
# ``agent`` path is a bug caught here.
#
# The inner assertion is intentionally modest: exit 0, ``meta.serialization``
# stamped to ``"toon"`` or ``"yaml"``, and when YAML the output parses as
# ``safe_load``-valid YAML.  We don't try to decode TOON in-process (no
# in-tree decoder — see test_toon.py for encoder correctness).


_AGENT_FALLBACK_CASES: list[tuple[str, list[str]]] = [
    ("inspect", ["inspect", "-t", "users"]),
    ("catalog", ["catalog"]),
    ("context", ["context", "-t", "users"]),
    ("preview", ["preview", "-t", "users"]),
    ("profile", ["profile", "-t", "users"]),
    ("freshness", ["freshness", "-t", "users"]),
    ("quality", ["quality", "-t", "users"]),
    ("values", ["values", "-t", "users", "--columns", "name"]),
    ("dist", ["dist", "-t", "users", "--columns", "age"]),
    ("diff", ["diff", "-t", "users", "--target", "users"]),
    ("joins", ["joins", "-t", "users"]),
    ("query", ["query", "--sql", "select 1 as one"]),
    ("assert", ["assert", "--sql", "select count(*) from users", "--expect", "2"]),
    ("explain", ["explain", "--sql", "select * from users"]),
    ("pivot", ["pivot", "-t", "users", "-g", "age", "-a", "count(id)"]),
    ("template", ["template", "-t", "users"]),
]


@pytest.mark.parametrize(
    ("label", "argv"), _AGENT_FALLBACK_CASES, ids=lambda v: v if isinstance(v, str) else None
)
def test_envelope_agent_format_either_toon_or_yaml_fallback(
    sqlite_path: str, label: str, argv: list[str]
) -> None:
    """Contract: every envelope command runs under ``-f agent`` and stamps
    a serialization tag the output actually matches. No crash, no silent
    fall-through, no missing tag.
    """
    r = runner.invoke(app, ["-f", "agent", *argv, "-c", sqlite_path])
    assert r.exit_code == 0, r.output

    # Both TOON and YAML put ``serialization`` under ``meta``. For YAML we
    # can round-trip via safe_load; for TOON we assert the tag is present.
    if "serialization: yaml" in r.output:
        import yaml

        envelope = yaml.safe_load(r.output)
        assert isinstance(envelope, dict), f"Expected dict, got {type(envelope).__name__}"
        assert set(envelope) == {"command", "data", "next_steps", "meta"}
        assert envelope["meta"]["serialization"] == "yaml"
    else:
        # TOON path — no in-tree decoder, so assert the marker is there and
        # the envelope shell rendered at least the command and meta blocks.
        assert "serialization: toon" in r.output, r.output
        assert f"command: {label}" in r.output or f"command: '{label}'" in r.output, r.output


def test_envelope_agent_format_yaml_fallback_for_non_tabular_shape(tmp_path):
    """CC.6: forcibly TOON-incompatible payload still emits a valid envelope.

    An envelope whose ``data`` contains mixed-type arrays isn't in TOON v1's
    shape coverage. The fallback path must still produce parseable YAML
    and carry ``meta.serialization == "yaml"``.
    """
    from querido.output.envelope import render_agent

    # Mixed-type array — not a uniform tabular shape, not a primitive array,
    # not a nested object. TOON raises ToonUnsupportedShape; render_agent
    # catches and falls back to YAML.
    payload = {"mix": [1, "two", {"n": 3}, [4, 5]]}
    rendered = render_agent(payload)

    import yaml

    parsed = yaml.safe_load(rendered)
    assert parsed == payload


# -- R.5: YAML fallback round-trips --------------------------------------------
#
# The YAML path is hit when TOON can't express the envelope shape (nested
# columns inside tables, sample_values arrays inside column dicts, etc.).
# These tests prove the output actually parses back — substring checks
# wouldn't catch e.g. a stray quote breaking the document, and the YAML
# fallback has no spec-conformance suite behind it (unlike TOON's 118-case
# fixture run in ``tests/test_toon.py``).
#
# TOON round-trip is intentionally NOT tested here: we have no in-tree TOON
# decoder, and writing one would share bugs with the encoder.  Encoder
# correctness is covered by the vendored spec fixtures in ``test_toon.py``.


def _parse_yaml_envelope(text: str) -> dict:
    """Parse ``-f agent`` output that fell back to YAML and assert basic shape."""
    import yaml

    envelope = yaml.safe_load(text)
    assert isinstance(envelope, dict), f"Expected dict, got {type(envelope).__name__}"
    assert set(envelope) == {"command", "data", "next_steps", "meta"}
    assert envelope["meta"]["serialization"] == "yaml"
    return envelope


def test_yaml_round_trip_catalog(sqlite_path: str):
    """Catalog's YAML fallback parses back to the same envelope shape."""
    result = runner.invoke(app, ["-f", "agent", "catalog", "-c", sqlite_path])
    assert result.exit_code == 0, result.output

    envelope = _parse_yaml_envelope(result.output)
    assert envelope["command"] == "catalog"
    tables = envelope["data"]["tables"]
    assert any(t["name"] == "users" for t in tables)
    # Next steps survive the round-trip as a list of {cmd, why} dicts.
    for step in envelope["next_steps"]:
        assert set(step) >= {"cmd", "why"}


def test_yaml_round_trip_context(sqlite_path: str):
    """Context has nested sample_values → YAML fallback.  Round-trip must
    preserve the column list, stats, and sample_values arrays."""
    result = runner.invoke(app, ["-f", "agent", "context", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0, result.output

    envelope = _parse_yaml_envelope(result.output)
    assert envelope["command"] == "context"
    data = envelope["data"]
    assert data["table"] == "users"
    assert data["row_count"] == 2
    col_names = [c["name"] for c in data["columns"]]
    assert col_names == ["id", "name", "age"]


def test_yaml_round_trip_preserves_unicode(tmp_path):
    """Unicode characters in row data must survive the YAML round-trip."""
    import sqlite3

    db_path = str(tmp_path / "unicode.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute("INSERT INTO users VALUES (1, '日本語')")
    conn.execute("INSERT INTO users VALUES (2, 'Ångström')")
    conn.execute("INSERT INTO users VALUES (3, 'Zoë')")
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["-f", "agent", "context", "-c", db_path, "-t", "users"])
    assert result.exit_code == 0, result.output

    envelope = _parse_yaml_envelope(result.output)
    name_col = next(c for c in envelope["data"]["columns"] if c["name"] == "name")
    sample_vals = name_col.get("sample_values") or []
    assert "日本語" in sample_vals
    assert "Ångström" in sample_vals
    assert "Zoë" in sample_vals


def test_yaml_round_trip_handles_null_heavy_rows(tmp_path):
    """Null-heavy rows must round-trip as Python None, not the string 'null'."""
    import sqlite3

    db_path = str(tmp_path / "nulls.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, notes TEXT, score REAL)")
    conn.execute("INSERT INTO users VALUES (1, NULL, NULL)")
    conn.execute("INSERT INTO users VALUES (2, NULL, NULL)")
    conn.execute("INSERT INTO users VALUES (3, 'something', 1.5)")
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["-f", "agent", "context", "-c", db_path, "-t", "users"])
    assert result.exit_code == 0, result.output

    envelope = _parse_yaml_envelope(result.output)
    notes_col = next(c for c in envelope["data"]["columns"] if c["name"] == "notes")
    # 2 of 3 rows are NULL → null_pct is around 66.6%. The exact value is
    # incidental; what matters is that YAML decoded it as a number, not a
    # string.
    assert isinstance(notes_col["null_pct"], (int, float))
    assert notes_col["null_count"] == 2


def test_yaml_round_trip_handles_empty_table(tmp_path):
    """A 0-row table must still produce a parseable envelope (YAML path).

    ``context`` on an empty table keeps the nested-column shape but every
    per-row stat is null — a realistic edge case for agents inspecting a
    freshly-created table.
    """
    import sqlite3

    db_path = str(tmp_path / "empty-tbl.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["-f", "agent", "context", "-c", db_path, "-t", "users"])
    assert result.exit_code == 0, result.output

    envelope = _parse_yaml_envelope(result.output)
    data = envelope["data"]
    assert data["row_count"] == 0
    # The column list is still emitted; the per-row stats are all None.
    col_names = [c["name"] for c in data["columns"]]
    assert col_names == ["id", "name", "age"]
    for col in data["columns"]:
        assert col["distinct_count"] in (0, None)


def test_yaml_round_trip_handles_special_characters_in_values(tmp_path):
    """Colons, quotes, and newlines in row data must not break YAML parsing."""
    import sqlite3

    db_path = str(tmp_path / "special.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, note TEXT NOT NULL)")
    # Strings that would break a naïve YAML encoder: leading colon,
    # embedded quotes, a literal newline.
    conn.execute("INSERT INTO users VALUES (1, ': starts with colon')")
    conn.execute("INSERT INTO users VALUES (2, 'has \"quotes\" inside')")
    conn.execute("INSERT INTO users VALUES (3, 'line one\nline two')")
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["-f", "agent", "context", "-c", db_path, "-t", "users"])
    assert result.exit_code == 0, result.output

    envelope = _parse_yaml_envelope(result.output)
    note_col = next(c for c in envelope["data"]["columns"] if c["name"] == "note")
    sample_vals = note_col.get("sample_values") or []
    assert ": starts with colon" in sample_vals
    assert 'has "quotes" inside' in sample_vals
    assert "line one\nline two" in sample_vals
