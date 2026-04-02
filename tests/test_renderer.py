import pytest

from querido.sql.renderer import render_template


def test_render_common_template():
    sql = render_template("test", "sqlite", table="users", limit=10)
    assert "select * from users limit 10" in sql


def test_render_falls_back_to_common():
    sql = render_template("test", "duckdb", table="orders", limit=5)
    assert "select * from orders limit 5" in sql


def test_dialect_specific_overrides_common():
    sql_sqlite = render_template("profile", "sqlite", columns=[], source="t")
    sql_duckdb = render_template("profile", "duckdb", columns=[], source="t")
    # Both dialect-specific templates exist; they should render (may differ)
    assert isinstance(sql_sqlite, str)
    assert isinstance(sql_duckdb, str)
    # UDF has separate sqlite/duckdb templates with distinct content
    cols = [{"name": "id", "type": "INTEGER"}]
    udf_sqlite = render_template("generate/udf", "sqlite", table="t", columns=cols)
    udf_duckdb = render_template("generate/udf", "duckdb", table="t", columns=cols)
    assert "create_function" in udf_sqlite
    assert "create or replace function" in udf_duckdb


def test_missing_template_raises_file_not_found():
    with pytest.raises(FileNotFoundError, match="No SQL template found"):
        render_template("nonexistent_command", "sqlite")


def test_template_rendering_with_columns_list():
    columns = [
        {"name": "id", "type": "INTEGER", "nullable": False, "primary_key": True, "default": None},
        {"name": "name", "type": "TEXT", "nullable": False, "primary_key": False, "default": None},
        {
            "name": "age",
            "type": "INTEGER",
            "nullable": True,
            "primary_key": False,
            "default": None,
        },
    ]
    sql = render_template("generate/select", "sqlite", table="users", columns=columns)
    assert "id," in sql
    assert "name," in sql
    assert "age" in sql
    assert "from users;" in sql


def test_template_rendering_with_conditionals():
    cols = [
        {"name": "x", "type": "INTEGER", "numeric": True},
        {"name": "y", "type": "TEXT", "numeric": False},
    ]
    sql = render_template("profile", "sqlite", columns=cols, source="t")
    assert "x" in sql
    assert "y" in sql
    assert "MIN_val" not in sql or "min_val" in sql.lower()


def test_env_singleton_is_reused():
    from querido.sql.renderer import _get_env

    env1 = _get_env()
    env2 = _get_env()
    assert env1 is env2
