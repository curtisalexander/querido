"""Tests for the JSON envelope + next_steps rules + try_next on errors.

The envelope wraps every scanning command's JSON output in a uniform shape::

    {command, data, next_steps, meta}

Rules live in :mod:`querido.core.next_steps` and are deterministic — given the
same shape of output, they produce the same next_steps list.
"""

from __future__ import annotations

import json
from typing import cast

import pytest
from typer.testing import CliRunner

from querido.cli.main import app
from querido.core import next_steps as ns
from querido.core.context import ContextResult
from querido.core.quality import QualityResult
from querido.core.values import ValuesResult
from querido.output.envelope import build_envelope, cmd, shell_quote_value

runner = CliRunner()


# -- envelope helpers ---------------------------------------------------------


def test_shell_quote_identifier_like_unquoted() -> None:
    assert shell_quote_value("orders") == "orders"
    assert shell_quote_value("my-db.orders_2024") == "my-db.orders_2024"


def test_shell_quote_path_with_slash_is_quoted() -> None:
    assert shell_quote_value("data/test.db") == "'data/test.db'"


def test_shell_quote_handles_single_quote() -> None:
    assert shell_quote_value("it's") == "'it'\\''s'"


def test_cmd_joins_argv_with_quoting() -> None:
    assert cmd(["qdo", "inspect", "-c", "data/test.db", "-t", "orders"]) == (
        "qdo inspect -c 'data/test.db' -t orders"
    )


def test_build_envelope_shape() -> None:
    env = build_envelope(
        command="inspect",
        data={"x": 1},
        next_steps=[{"cmd": "qdo foo", "why": "bar"}],
        connection="c",
        table="t",
    )
    assert env["command"] == "inspect"
    assert env["data"] == {"x": 1}
    assert env["next_steps"][0]["cmd"] == "qdo foo"
    assert env["meta"]["connection"] == "c"
    assert env["meta"]["table"] == "t"
    assert env["meta"]["qdo_version"]
    assert env["meta"]["generated_at"]


# -- inspect rules ------------------------------------------------------------


def test_for_inspect_nonempty_table_suggests_preview_and_context() -> None:
    result = {
        "row_count": 100,
        "columns": [{"name": "id"}, {"name": "name"}, {"name": "email"}],
        "table_comment": "A table",
    }
    steps = ns.for_inspect(result, connection="c", table="t", verbose=False)
    cmds = [s["cmd"] for s in steps]
    assert any("qdo preview" in c for c in cmds)
    assert any("qdo context" in c for c in cmds)
    assert any("qdo profile" in c and "--quick" in c for c in cmds)


def test_for_inspect_no_comment_suggests_metadata_init() -> None:
    result = {"row_count": 5, "columns": [{"name": "id"}], "table_comment": None}
    steps = ns.for_inspect(result, connection="c", table="t", verbose=False)
    assert any("qdo metadata init" in s["cmd"] for s in steps)


def test_for_inspect_empty_table_skips_preview() -> None:
    result = {"row_count": 0, "columns": [{"name": "id"}], "table_comment": "A table"}
    steps = ns.for_inspect(result, connection="c", table="t", verbose=False)
    cmds = [s["cmd"] for s in steps]
    assert not any("qdo preview" in c for c in cmds)


# -- catalog rules ------------------------------------------------------------


def test_for_catalog_picks_largest_table() -> None:
    result = {
        "tables": [
            {"name": "small", "row_count": 10},
            {"name": "big", "row_count": 10_000},
        ]
    }
    steps = ns.for_catalog(result, connection="c", enriched=False)
    assert any("qdo context" in s["cmd"] and "big" in s["cmd"] for s in steps)


def test_for_catalog_empty_nudges_to_config_test() -> None:
    steps = ns.for_catalog({"tables": []}, connection="c", enriched=False)
    assert len(steps) == 1
    assert steps[0]["cmd"] == "qdo config test c"


def test_for_catalog_join_suggestion_includes_source_table() -> None:
    result = {
        "tables": [
            {"name": "small", "row_count": 10},
            {"name": "big", "row_count": 10_000},
        ]
    }
    steps = ns.for_catalog(result, connection="c", enriched=False)
    assert any(s["cmd"] == "qdo joins -c c -t big" for s in steps)


def test_for_catalog_already_enriched_skips_enrich_suggestion() -> None:
    result = {"tables": [{"name": "t", "row_count": 1}]}
    steps = ns.for_catalog(result, connection="c", enriched=True)
    assert not any("--enrich" in s["cmd"] for s in steps)


def test_for_catalog_functions_sqlite_steps_back_to_catalog() -> None:
    steps = ns.for_catalog_functions(
        {"supported": False, "functions": []},
        connection="c",
        pattern=None,
    )
    assert steps[0]["cmd"] == "qdo catalog -c c"


def test_for_catalog_functions_empty_pattern_suggests_broadening() -> None:
    steps = ns.for_catalog_functions(
        {"supported": True, "functions": []},
        connection="c",
        pattern="geo",
    )
    assert any(s["cmd"] == "qdo catalog functions -c c" for s in steps)


def test_for_metadata_search_with_match_points_to_show_and_context() -> None:
    steps = ns.for_metadata_search(
        {
            "metadata_file_count": 1,
            "results": [{"table": "orders", "column": "customer_email"}],
        },
        connection="c",
    )
    cmds = [s["cmd"] for s in steps]
    assert "qdo metadata show -c c -t orders" in cmds
    assert "qdo context -c c -t orders" in cmds
    assert any('SELECT "customer_email"' in cmd for cmd in cmds)


def test_for_metadata_search_empty_index_points_to_list_and_catalog() -> None:
    steps = ns.for_metadata_search(
        {"metadata_file_count": 0, "results": []},
        connection="c",
    )
    cmds = [s["cmd"] for s in steps]
    assert "qdo metadata list -c c" in cmds
    assert "qdo catalog -c c" in cmds


# -- context rules ------------------------------------------------------------


def test_for_context_high_null_suggests_quality() -> None:
    result = {
        "row_count": 100,
        "columns": [{"name": "notes", "type": "TEXT", "null_pct": 80.0}],
    }
    steps = ns.for_context(cast(ContextResult, result), connection="c", table="t")
    assert any("qdo quality" in s["cmd"] for s in steps)


def test_for_context_low_cardinality_string_suggests_values() -> None:
    result = {
        "row_count": 100,
        "columns": [{"name": "status", "type": "VARCHAR", "distinct_count": 4}],
    }
    steps = ns.for_context(cast(ContextResult, result), connection="c", table="t")
    assert any("qdo values" in s["cmd"] and "--columns status" in s["cmd"] for s in steps)


def test_for_context_numeric_suggests_dist() -> None:
    result = {
        "row_count": 100,
        "columns": [{"name": "amount", "type": "DOUBLE", "null_pct": 0.0}],
    }
    steps = ns.for_context(cast(ContextResult, result), connection="c", table="t")
    assert any("qdo dist" in s["cmd"] and "--columns amount" in s["cmd"] for s in steps)


def test_for_freshness_without_selected_column_points_to_schema() -> None:
    steps = ns.for_freshness(
        {"selected_column": None, "status": "unknown"},
        connection="c",
        table="t",
    )
    assert any("qdo inspect" in s["cmd"] for s in steps)
    assert any("qdo context" in s["cmd"] for s in steps)


def test_for_freshness_stale_suggests_latest_rows_query() -> None:
    steps = ns.for_freshness(
        {"selected_column": "updated_at", "status": "stale"},
        connection="c",
        table="t",
    )
    assert any('order by "updated_at" desc limit 20' in s["cmd"] for s in steps)
    assert any("qdo quality" in s["cmd"] for s in steps)


# -- envelope contract --------------------------------------------------------
#
# Every command listed here must emit a uniform ``{command, data, next_steps,
# meta}`` envelope under ``-f json``.  Adding a scanning command without
# adding it to this parametrize list — or adding one that skips the envelope
# — is a bug (see PLAN.md R.2).  The ``expected_command`` field pins the
# ``command`` value; where subcommands use a space-joined form (bundle,
# workflow, etc.) those get their own contract test or are audited in R.10.


_ENVELOPE_CASES: list[tuple[str, list[str], str]] = [
    ("inspect", ["inspect", "-t", "users"], "inspect"),
    ("catalog", ["catalog"], "catalog"),
    ("context", ["context", "-t", "users"], "context"),
    ("preview", ["preview", "-t", "users"], "preview"),
    ("profile", ["profile", "-t", "users"], "profile"),
    ("freshness", ["freshness", "-t", "users"], "freshness"),
    ("quality", ["quality", "-t", "users"], "quality"),
    ("values", ["values", "-t", "users", "--columns", "name"], "values"),
    ("dist", ["dist", "-t", "users", "--columns", "age"], "dist"),
    ("diff", ["diff", "-t", "users", "--target", "users"], "diff"),
    ("joins", ["joins", "-t", "users"], "joins"),
    ("query", ["query", "--sql", "select 1 as one"], "query"),
    # R.2 — wired through emit_envelope alongside the original scanning set.
    (
        "assert",
        ["assert", "--sql", "select count(*) from users", "--expect", "2"],
        "assert",
    ),
    ("explain", ["explain", "--sql", "select * from users"], "explain"),
    (
        "pivot",
        ["pivot", "-t", "users", "-g", "age", "-a", "count(id)"],
        "pivot",
    ),
    ("template", ["template", "-t", "users"], "template"),
]


@pytest.mark.parametrize(("label", "argv", "expected_command"), _ENVELOPE_CASES, ids=lambda v: v)
def test_command_emits_envelope(
    sqlite_path: str, label: str, argv: list[str], expected_command: str
) -> None:
    """Contract: every envelope-emitting scan command returns the uniform shape."""
    r = runner.invoke(app, ["-f", "json", *argv, "-c", sqlite_path])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert set(payload) == {"command", "data", "next_steps", "meta"}
    assert payload["command"] == expected_command
    # next_steps may be empty for some edge shapes (e.g. trivial diff) but the
    # field must exist as a list.
    assert isinstance(payload["next_steps"], list)
    for step in payload["next_steps"]:
        assert step["cmd"].startswith(("qdo ", "uv "))
        assert step["why"]
    assert payload["meta"].get("connection") == sqlite_path


def test_envelope_meta_carries_table_when_applicable(sqlite_path: str) -> None:
    """Table-scoped commands echo the table back in ``meta.table``."""
    r = runner.invoke(app, ["-f", "json", "context", "-c", sqlite_path, "-t", "users"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["meta"]["table"] == "users"


def test_metadata_show_emits_envelope(sqlite_path: str, tmp_path, monkeypatch) -> None:
    """CS.3 regression — ``metadata show`` must emit the uniform envelope.

    Requires ``metadata init`` first so the YAML exists. Isolated to a
    temp working dir so `.qdo/metadata/` writes don't collide across tests.
    """
    monkeypatch.chdir(tmp_path)
    init_result = runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])
    assert init_result.exit_code == 0, init_result.output

    r = runner.invoke(app, ["-f", "json", "metadata", "show", "-c", sqlite_path, "-t", "users"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert set(payload) == {"command", "data", "next_steps", "meta"}
    assert payload["command"] == "metadata show"
    assert isinstance(payload["next_steps"], list)
    # Every next_step points at the same connection + table.
    for step in payload["next_steps"]:
        assert sqlite_path in step["cmd"]
        assert "users" in step["cmd"]
    assert payload["meta"]["table"] == "users"


def test_metadata_search_emits_envelope(sqlite_path: str, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init_result = runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])
    assert init_result.exit_code == 0, init_result.output

    r = runner.invoke(app, ["-f", "json", "metadata", "search", "-c", sqlite_path, "alice"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert set(payload) == {"command", "data", "next_steps", "meta"}
    assert payload["command"] == "metadata search"
    assert isinstance(payload["next_steps"], list)
    assert payload["meta"]["connection"] == sqlite_path


def test_for_metadata_show_suggests_edit_and_refresh() -> None:
    """Unit: the rule always returns edit + refresh; placeholders add suggest."""
    from querido.core.next_steps import for_metadata_show

    meta_no_placeholders = {
        "table_description": "Real description.",
        "columns": [{"name": "id", "description": "Primary key."}],
    }
    steps = for_metadata_show(meta_no_placeholders, connection="c", table="t")
    cmds = [s["cmd"] for s in steps]
    assert any("metadata edit" in c for c in cmds)
    assert any("metadata refresh" in c for c in cmds)
    assert not any("metadata suggest" in c for c in cmds)

    meta_with_placeholder = {
        "table_description": "<description>",
        "columns": [{"name": "id"}],
    }
    steps = for_metadata_show(meta_with_placeholder, connection="c", table="t")
    assert any("metadata suggest" in s["cmd"] for s in steps)


def test_view_def_emits_envelope(tmp_path) -> None:
    """view-def needs a view in the db; covered separately from _ENVELOPE_CASES."""
    import sqlite3

    db_path = str(tmp_path / "viewtest.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("CREATE VIEW active_users AS SELECT id, name FROM users")
    conn.commit()
    conn.close()

    r = runner.invoke(app, ["-f", "json", "view-def", "--view", "active_users", "-c", db_path])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert set(payload) == {"command", "data", "next_steps", "meta"}
    assert payload["command"] == "view-def"
    assert isinstance(payload["next_steps"], list)
    assert payload["meta"]["table"] == "active_users"


# -- R.10: envelope ``command`` field must match argv shape -------------------
#
# Agents re-exec invocations by reading ``command`` back; the value must
# equal ``argv[0:n]`` joined by single spaces. Leaf commands are a single
# token ("inspect"), nested commands are space-joined ("bundle export",
# "workflow list"). Adding a new envelope-emitting subcommand without
# updating this list is a bug.


_MULTIWORD_COMMAND_CASES: list[tuple[list[str], str]] = [
    (["workflow", "list"], "workflow list"),
    # ``metadata show`` is covered by test_metadata_show_emits_envelope which
    # also needs a metadata-init prelude; kept out of this parametrization.
]


@pytest.mark.parametrize(("argv", "expected_command"), _MULTIWORD_COMMAND_CASES)
def test_envelope_command_matches_argv_for_multiword_commands(
    argv: list[str], expected_command: str
) -> None:
    """Nested commands emit ``command`` as a space-joined argv prefix."""
    r = runner.invoke(app, ["-f", "json", *argv])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["command"] == expected_command


def test_catalog_functions_emits_envelope(duckdb_path: str) -> None:
    r = runner.invoke(app, ["-f", "json", "catalog", "functions", "-c", duckdb_path])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert set(payload) == {"command", "data", "next_steps", "meta"}
    assert payload["command"] == "catalog functions"
    assert payload["meta"]["connection"] == duckdb_path


# -- try_next on errors -------------------------------------------------------


def test_error_json_file_not_found_includes_try_next(tmp_path) -> None:
    r = runner.invoke(app, ["-f", "json", "inspect", "-c", str(tmp_path / "nope.db"), "-t", "x"])
    assert r.exit_code != 0
    # JSON error payload is written to stderr; CliRunner merges by default
    # via mix_stderr=True (Typer 0.12+).  Try parsing the last JSON object
    # in the combined stream.
    blob = r.output
    start = blob.find("{")
    assert start >= 0, blob
    err = json.loads(blob[start:])
    assert err["error"] is True
    assert err["code"] == "FILE_NOT_FOUND"
    assert err["try_next"], err
    assert err["try_next"][0]["cmd"].startswith("qdo ")


def test_for_error_database_open_failed_uses_positional_config_test() -> None:
    steps = ns.for_error("DATABASE_OPEN_FAILED", connection="demo")
    assert steps[0]["cmd"] == "qdo config test demo"


def test_for_error_auth_failed_uses_positional_config_test() -> None:
    steps = ns.for_error("AUTH_FAILED", connection="demo")
    assert steps[0]["cmd"] == "qdo config test demo"


def test_for_error_table_not_found_includes_catalog_suggestion() -> None:
    steps = ns.for_error("TABLE_NOT_FOUND", connection="c", table="orders")
    assert any("qdo catalog" in s["cmd"] for s in steps)
    assert any("--pattern orders" in s["cmd"] for s in steps)


def test_for_error_missing_connection_skips_suggestions_needing_it() -> None:
    steps = ns.for_error("COLUMN_NOT_FOUND", connection=None, table=None)
    assert steps == []


# -- rules for the fan-out 8 --------------------------------------------------


def test_for_preview_empty_result_suggests_inspect() -> None:
    steps = ns.for_preview([], connection="c", table="t", limit=20)
    assert any("qdo inspect" in s["cmd"] for s in steps)


def test_for_preview_hit_limit_suggests_more_rows() -> None:
    steps = ns.for_preview([{"x": 1}] * 5, connection="c", table="t", limit=5)
    assert any("--rows 25" in s["cmd"] for s in steps)


def test_for_profile_low_card_string_suggests_values() -> None:
    result = {
        "columns": [
            {"column_name": "status", "distinct_count": 3, "min_length": 1, "null_pct": 0.0},
        ],
        "sampled": False,
    }
    steps = ns.for_profile(result, connection="c", table="t", top=0)
    assert any("qdo values" in s["cmd"] and "--columns status" in s["cmd"] for s in steps)


def test_for_profile_numeric_suggests_dist() -> None:
    result = {
        "columns": [
            {"column_name": "amount", "min_val": 0, "mean_val": 10.0, "null_pct": 0.0},
        ],
        "sampled": False,
    }
    steps = ns.for_profile(result, connection="c", table="t", top=0)
    assert any("qdo dist" in s["cmd"] and "--columns amount" in s["cmd"] for s in steps)


def test_for_profile_sampled_suggests_no_sample() -> None:
    result = {"columns": [], "sampled": True}
    steps = ns.for_profile(result, connection="c", table="t", top=5)
    assert any("--no-sample" in s["cmd"] for s in steps)


def test_for_dist_categorical_many_values_suggests_values() -> None:
    result = {
        "column": "city",
        "mode": "categorical",
        "values": [{"value": f"c{i}", "count": 1} for i in range(25)],
        "null_count": 0,
    }
    steps = ns.for_dist(result, connection="c", table="t")
    assert any("qdo values" in s["cmd"] for s in steps)


def test_for_dist_with_nulls_suggests_quality() -> None:
    result = {"column": "email", "mode": "numeric", "null_count": 7}
    steps = ns.for_dist(result, connection="c", table="t")
    assert any("qdo quality" in s["cmd"] and "--columns email" in s["cmd"] for s in steps)


def test_for_values_truncated_suggests_raising_max() -> None:
    result = {"column": "x", "truncated": True, "distinct_count": 5000}
    steps = ns.for_values(cast(ValuesResult, result), connection="c", table="t")
    assert any("--max" in s["cmd"] for s in steps)


def test_for_values_enumerable_suggests_capture() -> None:
    result = {"column": "x", "truncated": False, "distinct_count": 4}
    steps = ns.for_values(cast(ValuesResult, result), connection="c", table="t")
    assert any("qdo values" in s["cmd"] and "--write-metadata" in s["cmd"] for s in steps)


def test_for_values_skips_capture_when_already_stored() -> None:
    """Don't nag about capturing valid_values that are already on disk."""
    result = {
        "column": "x",
        "truncated": False,
        "distinct_count": 4,
        "stored_metadata": {"valid_values": ["a", "b", "c", "d"]},
    }
    steps = ns.for_values(cast(ValuesResult, result), connection="c", table="t")
    assert not any("--write-metadata" in s["cmd"] for s in steps)


def test_for_quality_failing_column_triggers_dist_and_values() -> None:
    result = {
        "columns": [{"name": "notes", "status": "fail"}],
        "duplicate_rows": None,
    }
    steps = ns.for_quality(cast(QualityResult, result), connection="c", table="t")
    assert any("qdo dist" in s["cmd"] and "--columns notes" in s["cmd"] for s in steps)
    assert any("qdo values" in s["cmd"] and "--columns notes" in s["cmd"] for s in steps)
    assert any("--check-duplicates" in s["cmd"] for s in steps)


def test_for_diff_identical_suggests_context() -> None:
    result = {"added": [], "removed": [], "changed": []}
    steps = ns.for_diff(
        result, connection="c", left_table="l", right_table="r", target_connection=None
    )
    assert len(steps) == 1
    assert "qdo context" in steps[0]["cmd"]


def test_for_diff_divergent_suggests_inspect_both_sides() -> None:
    result = {"added": [{"name": "new"}], "removed": [], "changed": []}
    steps = ns.for_diff(
        result, connection="A", left_table="l", right_table="r", target_connection="B"
    )
    assert any("qdo inspect -c A -t l" in s["cmd"] for s in steps)
    assert any("qdo inspect -c B -t r" in s["cmd"] for s in steps)


def test_for_joins_no_candidates_steps_out_to_catalog() -> None:
    steps = ns.for_joins({"candidates": []}, connection="c", source_table="orders")
    assert len(steps) == 1
    assert "qdo catalog" in steps[0]["cmd"]


def test_for_joins_builds_try_join_sql() -> None:
    result = {
        "candidates": [
            {
                "target_table": "customers",
                "join_keys": [
                    {"source_col": "customer_id", "target_col": "id", "confidence": 0.9}
                ],
            }
        ]
    }
    steps = ns.for_joins(result, connection="c", source_table="orders")
    # Top suggestion should be a test-join query
    query_step = next((s for s in steps if "qdo query" in s["cmd"]), None)
    assert query_step is not None
    assert "join customers" in query_step["cmd"]
    assert "l.customer_id = r.id" in query_step["cmd"]


def test_for_query_no_rows_suggests_catalog() -> None:
    steps = ns.for_query({"rows": [], "limited": False}, connection="c")
    assert any("qdo catalog" in s["cmd"] for s in steps)


def test_for_query_limit_hit_suggests_export() -> None:
    steps = ns.for_query({"rows": [{"x": 1}], "limited": True}, connection="c")
    assert any("qdo export" in s["cmd"] for s in steps)
    # for_query points at --export-format, not the global --format; the two
    # flags are different and the latter is a no-op on export.
    assert any("--export-format" in s["cmd"] for s in steps)


# -- rules for the R.2 commands -----------------------------------------------


def test_for_assert_passed_no_next_steps() -> None:
    steps = ns.for_assert({"passed": True, "sql": "select 1"}, connection="c")
    assert steps == []


def test_for_assert_failed_points_at_underlying_query() -> None:
    result = {"passed": False, "sql": "select count(*) from orders"}
    steps = ns.for_assert(result, connection="c")
    assert len(steps) == 1
    assert "qdo query" in steps[0]["cmd"]
    assert "select count(*) from orders" in steps[0]["cmd"]


def test_for_explain_always_suggests_running_the_query() -> None:
    result = {"sql": "select * from users", "dialect": "sqlite", "analyzed": False}
    steps = ns.for_explain(result, connection="c")
    assert any("qdo query" in s["cmd"] for s in steps)


def test_for_explain_duckdb_non_analyzed_suggests_analyze() -> None:
    result = {"sql": "select * from users", "dialect": "duckdb", "analyzed": False}
    steps = ns.for_explain(result, connection="c")
    assert any("--analyze" in s["cmd"] for s in steps)


def test_for_explain_sqlite_does_not_suggest_analyze() -> None:
    """SQLite doesn't support EXPLAIN ANALYZE — don't offer it."""
    result = {"sql": "select * from users", "dialect": "sqlite", "analyzed": False}
    steps = ns.for_explain(result, connection="c")
    assert not any("--analyze" in s["cmd"] for s in steps)


def test_for_pivot_empty_suggests_preview_for_sanity_check() -> None:
    steps = ns.for_pivot({"rows": [], "sql": "select ..."}, connection="c", table="orders")
    assert len(steps) == 1
    assert "qdo preview" in steps[0]["cmd"]


def test_for_pivot_with_rows_suggests_iterate_and_context() -> None:
    result = {"rows": [{"region": "east", "sum_amount": 100}], "sql": "select ..."}
    steps = ns.for_pivot(result, connection="c", table="orders")
    cmds = [s["cmd"] for s in steps]
    assert any("qdo query" in c for c in cmds)
    assert any("qdo context" in c for c in cmds)


def test_for_view_def_points_at_inspect_and_preview() -> None:
    result = {"view": "active_users", "dialect": "sqlite", "definition": "select ..."}
    steps = ns.for_view_def(result, connection="c", view="active_users")
    cmds = [s["cmd"] for s in steps]
    assert any("qdo inspect" in c and "active_users" in c for c in cmds)
    assert any("qdo preview" in c and "active_users" in c for c in cmds)


def test_for_view_def_empty_definition_skips_suggestions() -> None:
    steps = ns.for_view_def({"definition": ""}, connection="c", view="v")
    assert steps == []


def test_for_template_no_comment_suggests_metadata_init() -> None:
    result = {
        "table": "orders",
        "table_comment": "",
        "columns": [{"name": "id"}],
    }
    steps = ns.for_template(result, connection="c", table="orders")
    assert any("metadata init" in s["cmd"] for s in steps)


def test_for_template_with_comment_skips_metadata_init() -> None:
    result = {
        "table": "orders",
        "table_comment": "Customer orders",
        "columns": [{"name": "id"}],
    }
    steps = ns.for_template(result, connection="c", table="orders")
    assert not any("metadata init" in s["cmd"] for s in steps)


def test_for_template_always_suggests_profile_write_metadata() -> None:
    """Template is the doc-authoring entrypoint — always nudge toward
    auto-capturing deterministic inferences when there are columns."""
    result = {
        "table": "orders",
        "table_comment": "Customer orders",
        "columns": [{"name": "id"}],
    }
    steps = ns.for_template(result, connection="c", table="orders")
    assert any("profile" in s["cmd"] and "--write-metadata" in s["cmd"] for s in steps)


# -- R.7: workflow step-failure rule ------------------------------------------


def test_for_workflow_step_failed_points_at_session_and_verbose_rerun() -> None:
    """Every step failure offers: session inspection, standalone cmd, verbose rerun."""
    steps = ns.for_workflow_step_failed(
        workflow="demo",
        step_id="inspect",
        step_cmd="qdo inspect -c ./x.db -t users",
        session="workflow-demo-123",
    )
    cmds = [s["cmd"] for s in steps]
    assert any("qdo session show workflow-demo-123" in c for c in cmds)
    assert any(c == "qdo inspect -c ./x.db -t users" for c in cmds)
    assert any("qdo workflow run demo --verbose" in c for c in cmds)


def test_for_workflow_step_failed_timeout_adds_disable_hint() -> None:
    """Timeout failures get an extra hint: --step-timeout 0 to disable."""
    steps = ns.for_workflow_step_failed(
        workflow="demo",
        step_id="slow",
        step_cmd="qdo profile -c ./x.db -t big",
        session="",
        timed_out=True,
    )
    assert any("--step-timeout 0" in s["cmd"] for s in steps)


def test_for_workflow_step_failed_empty_session_skips_session_step() -> None:
    """When the runner couldn't record a session, don't offer to show it."""
    steps = ns.for_workflow_step_failed(
        workflow="demo",
        step_id="s",
        step_cmd="qdo inspect -c ./x.db -t users",
        session="",
    )
    assert not any("qdo session show" in s["cmd"] for s in steps)


# -- end-to-end envelope checks on the fan-out 8 ------------------------------


def test_preview_json_has_envelope(sqlite_path: str) -> None:
    r = runner.invoke(app, ["-f", "json", "preview", "-c", sqlite_path, "-t", "users"])
    assert r.exit_code == 0, r.output
    p = json.loads(r.output)
    assert p["command"] == "preview"
    assert p["data"]["table"] == "users"
    assert isinstance(p["next_steps"], list)


def test_profile_json_has_envelope(sqlite_path: str) -> None:
    r = runner.invoke(app, ["-f", "json", "profile", "-c", sqlite_path, "-t", "users"])
    assert r.exit_code == 0, r.output
    p = json.loads(r.output)
    assert p["command"] == "profile"
    assert p["data"]["row_count"] == 2


def test_values_json_has_envelope(sqlite_path: str) -> None:
    r = runner.invoke(
        app, ["-f", "json", "values", "-c", sqlite_path, "-t", "users", "-C", "name"]
    )
    assert r.exit_code == 0, r.output
    p = json.loads(r.output)
    assert p["command"] == "values"
    assert p["data"]["column"] == "name"


def test_query_json_has_envelope(sqlite_path: str) -> None:
    r = runner.invoke(app, ["-f", "json", "query", "-c", sqlite_path, "--sql", "select 1 as n"])
    assert r.exit_code == 0, r.output
    p = json.loads(r.output)
    assert p["command"] == "query"
    assert p["data"]["rows"][0]["n"] == 1
