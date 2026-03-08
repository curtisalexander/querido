"""Tests for the querido.core layer."""

from querido.connectors.factory import create_connector

# --- core.preview ---


def test_get_preview_sqlite(sqlite_path: str) -> None:
    from querido.core.preview import get_preview

    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        rows = get_preview(conn, "users", limit=10)
    assert len(rows) == 2
    assert rows[0]["name"] == "Alice"


def test_get_preview_duckdb(duckdb_path: str) -> None:
    from querido.core.preview import get_preview

    with create_connector({"type": "duckdb", "path": duckdb_path}) as conn:
        rows = get_preview(conn, "users", limit=1)
    assert len(rows) == 1


def test_get_preview_default_limit(sqlite_path: str) -> None:
    from querido.core.preview import get_preview

    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        rows = get_preview(conn, "users")
    assert len(rows) == 2  # only 2 rows in test table


# --- core.inspect ---


def test_get_inspect_sqlite(sqlite_path: str) -> None:
    from querido.core.inspect import get_inspect

    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        result = get_inspect(conn, "users")
    assert result["row_count"] == 2
    assert len(result["columns"]) == 3
    assert result["table_comment"] is None
    col_names = [c["name"] for c in result["columns"]]
    assert "id" in col_names
    assert "name" in col_names
    assert "age" in col_names


def test_get_inspect_duckdb(duckdb_path: str) -> None:
    from querido.core.inspect import get_inspect

    with create_connector({"type": "duckdb", "path": duckdb_path}) as conn:
        result = get_inspect(conn, "users")
    assert result["row_count"] == 2
    assert len(result["columns"]) == 3


def test_get_inspect_verbose_duckdb(duckdb_with_comments_path: str) -> None:
    from querido.core.inspect import get_inspect

    with create_connector({"type": "duckdb", "path": duckdb_with_comments_path}) as conn:
        result = get_inspect(conn, "users", verbose=True)
    assert result["table_comment"] == "Application user accounts"


def test_get_inspect_verbose_sqlite(sqlite_path: str) -> None:
    from querido.core.inspect import get_inspect

    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        result = get_inspect(conn, "users", verbose=True)
    assert result["table_comment"] is None  # SQLite has no comment support


# --- core.profile ---


def test_get_profile_sqlite(sqlite_path: str) -> None:
    from querido.core.profile import get_profile

    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        result = get_profile(conn, "users")
    assert result["row_count"] == 2
    assert result["sampled"] is False
    assert result["sample_size"] is None
    assert len(result["stats"]) == 3  # one per column


def test_get_profile_duckdb(duckdb_path: str) -> None:
    from querido.core.profile import get_profile

    with create_connector({"type": "duckdb", "path": duckdb_path}) as conn:
        result = get_profile(conn, "users")
    assert result["row_count"] == 2
    assert len(result["stats"]) == 3


def test_get_profile_column_filter(sqlite_path: str) -> None:
    from querido.core.profile import get_profile

    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        result = get_profile(conn, "users", columns="name,age")
    assert len(result["stats"]) == 2
    col_names = [s["column_name"] for s in result["stats"]]
    assert "name" in col_names
    assert "age" in col_names


def test_get_profile_invalid_column_filter(sqlite_path: str) -> None:
    import pytest

    from querido.core.profile import get_profile

    with (
        create_connector({"type": "sqlite", "path": sqlite_path}) as conn,
        pytest.raises(ValueError, match="No matching columns"),
    ):
        get_profile(conn, "users", columns="nonexistent")


def test_get_frequencies(sqlite_path: str) -> None:
    from querido.core.profile import get_frequencies, get_profile

    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        result = get_profile(conn, "users")
        freq = get_frequencies(conn, result["source"], result["col_info"], top=5)
    assert "name" in freq
    assert len(freq["name"]) <= 5


def test_is_numeric_type() -> None:
    from querido.core.profile import is_numeric_type

    assert is_numeric_type("INTEGER")
    assert is_numeric_type("BIGINT")
    assert is_numeric_type("float")
    assert is_numeric_type("DECIMAL(10,2)")
    assert is_numeric_type("NUMBER")
    assert not is_numeric_type("VARCHAR")
    assert not is_numeric_type("TEXT")
    assert not is_numeric_type("DATE")


# --- core.search ---


def test_search_metadata_tables(sqlite_path: str) -> None:
    from querido.core.search import search_metadata

    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        results = search_metadata(conn, "user", "table")
    assert len(results) == 1
    assert results[0]["table_name"] == "users"
    assert results[0]["match_type"] == "table"


def test_search_metadata_columns(sqlite_path: str) -> None:
    from querido.core.search import search_metadata

    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        results = search_metadata(conn, "name", "column")
    assert len(results) == 1
    assert results[0]["column_name"] == "name"
    assert results[0]["match_type"] == "column"


def test_search_metadata_all(sqlite_path: str) -> None:
    from querido.core.search import search_metadata

    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        results = search_metadata(conn, "user", "all")
    # Should match table "users" and possibly columns
    table_matches = [r for r in results if r["match_type"] == "table"]
    assert len(table_matches) >= 1


def test_search_no_results(sqlite_path: str) -> None:
    from querido.core.search import search_metadata

    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        results = search_metadata(conn, "zzzznonexistent", "all")
    assert results == []


def test_try_cached_search_no_cache() -> None:
    from querido.core.search import try_cached_search

    # No cache exists, should return None gracefully
    result = try_cached_search("nonexistent_conn", "pattern", "all")
    assert result is None


# --- core.dist ---


def test_get_distribution_numeric_sqlite(sqlite_path: str) -> None:
    from querido.core.dist import get_distribution

    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        result = get_distribution(conn, "users", "age", buckets=5)
    assert result["mode"] == "numeric"
    assert result["total_rows"] == 2
    assert result["column"] == "age"
    assert "buckets" in result


def test_get_distribution_categorical_sqlite(sqlite_path: str) -> None:
    from querido.core.dist import get_distribution

    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        result = get_distribution(conn, "users", "name", top=10)
    assert result["mode"] == "categorical"
    assert result["total_rows"] == 2
    assert "values" in result


def test_get_distribution_duckdb(duckdb_path: str) -> None:
    from querido.core.dist import get_distribution

    with create_connector({"type": "duckdb", "path": duckdb_path}) as conn:
        result = get_distribution(conn, "users", "age", buckets=5)
    assert result["mode"] == "numeric"
    assert result["total_rows"] == 2


# --- core.lineage ---


def test_get_view_definition_sqlite(sqlite_path: str) -> None:
    import sqlite3

    from querido.core.lineage import get_view_definition

    # Create a view first
    raw = sqlite3.connect(sqlite_path)
    raw.execute("CREATE VIEW young_users AS SELECT * FROM users WHERE age < 30")
    raw.commit()
    raw.close()

    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        result = get_view_definition(conn, "young_users")
    assert result["view"] == "young_users"
    assert result["dialect"] == "sqlite"
    assert "SELECT" in result["definition"]


def test_get_view_definition_not_found(sqlite_path: str) -> None:
    import pytest

    from querido.core.lineage import get_view_definition

    with (
        create_connector({"type": "sqlite", "path": sqlite_path}) as conn,
        pytest.raises(LookupError, match="not a view"),
    ):
        get_view_definition(conn, "users")


# --- core.template ---


def test_get_template_sqlite(sqlite_path: str) -> None:
    from querido.core.template import get_template

    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        result = get_template(conn, "users", sample_values=2)
    assert result["table"] == "users"
    assert result["row_count"] == 2
    assert len(result["columns"]) == 3
    col_names = [c["name"] for c in result["columns"]]
    assert "id" in col_names
    assert "name" in col_names


def test_get_template_no_samples(sqlite_path: str) -> None:
    from querido.core.template import get_template

    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        result = get_template(conn, "users", sample_values=0)
    # Should still work, just no sample values
    for col in result["columns"]:
        assert col["sample_values"] == ""


def test_get_template_duckdb(duckdb_path: str) -> None:
    from querido.core.template import get_template

    with create_connector({"type": "duckdb", "path": duckdb_path}) as conn:
        result = get_template(conn, "users")
    assert result["table"] == "users"
    assert result["row_count"] == 2
    assert len(result["columns"]) == 3
