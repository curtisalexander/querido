"""Tests for the JSON envelope + next_steps rules + try_next on errors.

The envelope wraps every scanning command's JSON output in a uniform shape::

    {command, data, next_steps, meta}

Rules live in :mod:`querido.core.next_steps` and are deterministic — given the
same shape of output, they produce the same next_steps list.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from querido.cli.main import app
from querido.core import next_steps as ns
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
    assert "qdo config test" in steps[0]["cmd"]


def test_for_catalog_already_enriched_skips_enrich_suggestion() -> None:
    result = {"tables": [{"name": "t", "row_count": 1}]}
    steps = ns.for_catalog(result, connection="c", enriched=True)
    assert not any("--enrich" in s["cmd"] for s in steps)


# -- context rules ------------------------------------------------------------


def test_for_context_high_null_suggests_quality() -> None:
    result = {
        "row_count": 100,
        "columns": [{"name": "notes", "type": "TEXT", "null_pct": 80.0}],
    }
    steps = ns.for_context(result, connection="c", table="t")
    assert any("qdo quality" in s["cmd"] for s in steps)


def test_for_context_low_cardinality_string_suggests_values() -> None:
    result = {
        "row_count": 100,
        "columns": [{"name": "status", "type": "VARCHAR", "distinct_count": 4}],
    }
    steps = ns.for_context(result, connection="c", table="t")
    assert any("qdo values" in s["cmd"] and "--column status" in s["cmd"] for s in steps)


def test_for_context_numeric_suggests_dist() -> None:
    result = {
        "row_count": 100,
        "columns": [{"name": "amount", "type": "DOUBLE", "null_pct": 0.0}],
    }
    steps = ns.for_context(result, connection="c", table="t")
    assert any("qdo dist" in s["cmd"] and "--column amount" in s["cmd"] for s in steps)


# -- end-to-end JSON shape ----------------------------------------------------


def test_inspect_json_has_envelope(sqlite_path: str) -> None:
    r = runner.invoke(app, ["-f", "json", "inspect", "-c", sqlite_path, "-t", "users"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert set(payload) == {"command", "data", "next_steps", "meta"}
    assert payload["command"] == "inspect"
    assert payload["next_steps"], "expected at least one next_step"
    for step in payload["next_steps"]:
        assert step["cmd"].startswith(("qdo ", "uv "))
        assert step["why"]


def test_catalog_json_has_envelope(sqlite_path: str) -> None:
    r = runner.invoke(app, ["-f", "json", "catalog", "-c", sqlite_path])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["command"] == "catalog"
    assert "tables" in payload["data"]
    assert payload["next_steps"]


def test_context_json_has_envelope(sqlite_path: str) -> None:
    r = runner.invoke(app, ["-f", "json", "context", "-c", sqlite_path, "-t", "users"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["command"] == "context"
    assert payload["data"]["table"] == "users"
    assert payload["meta"]["connection"] == sqlite_path
    assert payload["meta"]["table"] == "users"


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
    assert any("qdo values" in s["cmd"] and "--column status" in s["cmd"] for s in steps)


def test_for_profile_numeric_suggests_dist() -> None:
    result = {
        "columns": [
            {"column_name": "amount", "min_val": 0, "mean_val": 10.0, "null_pct": 0.0},
        ],
        "sampled": False,
    }
    steps = ns.for_profile(result, connection="c", table="t", top=0)
    assert any("qdo dist" in s["cmd"] and "--column amount" in s["cmd"] for s in steps)


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
    steps = ns.for_values(result, connection="c", table="t")
    assert any("--max" in s["cmd"] for s in steps)


def test_for_values_enumerable_suggests_metadata_edit() -> None:
    result = {"column": "x", "truncated": False, "distinct_count": 4}
    steps = ns.for_values(result, connection="c", table="t")
    assert any("qdo metadata edit" in s["cmd"] for s in steps)


def test_for_quality_failing_column_triggers_dist_and_values() -> None:
    result = {
        "columns": [{"name": "notes", "status": "fail"}],
        "duplicate_rows": None,
    }
    steps = ns.for_quality(result, connection="c", table="t")
    assert any("qdo dist" in s["cmd"] and "--column notes" in s["cmd"] for s in steps)
    assert any("qdo values" in s["cmd"] and "--column notes" in s["cmd"] for s in steps)
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
