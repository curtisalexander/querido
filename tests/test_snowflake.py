"""Mocked tests for the Snowflake connector.

Tests connector behavior, Arrow integration, auth routing, and
connections.toml support — all without a real Snowflake account.
"""

import sys
import types
from unittest.mock import MagicMock

import pyarrow as pa

# ---------------------------------------------------------------------------
# Fake snowflake module — injected into sys.modules so the connector can
# `import snowflake.connector` without the real package installed.
# ---------------------------------------------------------------------------

_mock_connect = MagicMock()

_fake_snowflake = types.ModuleType("snowflake")
_fake_snowflake.__path__ = []  # mark as package
_fake_connector = types.ModuleType("snowflake.connector")
_fake_connector.connect = _mock_connect  # type: ignore[attr-defined]
_fake_snowflake.connector = _fake_connector  # type: ignore[attr-defined]

sys.modules.setdefault("snowflake", _fake_snowflake)
sys.modules.setdefault("snowflake.connector", _fake_connector)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_cursor(arrow_batches: list[pa.RecordBatch] | None = None, rows=None, columns=None):
    """Build a mock Snowflake cursor with optional Arrow and standard fetch."""
    cursor = MagicMock()
    if columns:
        cursor.description = [(c, None, None, None, None, None, None) for c in columns]
    else:
        cursor.description = None

    if arrow_batches is not None:
        cursor.fetch_arrow_batches.return_value = iter(arrow_batches)
    else:
        cursor.fetch_arrow_batches.side_effect = RuntimeError("no arrow")

    if rows is not None:
        cursor.fetchall.return_value = rows
    else:
        cursor.fetchall.return_value = []

    return cursor


def _make_connector(*, _session_db="TEST_DB", _session_schema="PUBLIC", **connect_kwargs):
    """Create a SnowflakeConnector with a mocked snowflake.connector.connect.

    *_session_db* and *_session_schema* control what ``CURRENT_DATABASE()`` /
    ``CURRENT_SCHEMA()`` return when the connector falls back to querying the
    session (i.e. when database/schema are not in the config).  Pass empty
    strings to simulate a session with no defaults.
    """
    _mock_connect.reset_mock()
    mock_conn = MagicMock()
    _mock_connect.return_value = mock_conn

    # The __init__ runs SELECT CURRENT_DATABASE(), CURRENT_SCHEMA()
    # via a cursor, so set up the init cursor to return test values.
    init_cursor = MagicMock()
    init_cursor.fetchone.return_value = (_session_db or None, _session_schema or None)
    mock_conn.cursor.return_value = init_cursor

    from querido.connectors.snowflake import SnowflakeConnector

    connector = SnowflakeConnector(**connect_kwargs)
    return connector, mock_conn, _mock_connect


# ---------------------------------------------------------------------------
# Connection / Auth tests
# ---------------------------------------------------------------------------


class TestSnowflakeConnection:
    def test_basic_connect_params(self):
        """Standard account/user/password params pass through."""
        connector, _, mock_connect = _make_connector(
            type="snowflake",
            account="test-account",
            user="testuser",
            password="secret",
        )
        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["account"] == "test-account"
        assert call_kwargs["user"] == "testuser"
        assert call_kwargs["password"] == "secret"
        assert connector.dialect == "snowflake"

    def test_auth_maps_to_authenticator(self):
        """qdo's 'auth' key becomes Snowflake's 'authenticator'."""
        _, _, mock_connect = _make_connector(
            type="snowflake",
            account="test-account",
            user="testuser",
            auth="externalbrowser",
        )
        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["authenticator"] == "externalbrowser"
        assert "auth" not in call_kwargs

    def test_snowflake_connection_name(self):
        """snowflake_connection maps to connection_name for native connections.toml."""
        _, _, mock_connect = _make_connector(
            type="snowflake",
            snowflake_connection="my-named-conn",
        )
        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["connection_name"] == "my-named-conn"
        assert "snowflake_connection" not in call_kwargs

    def test_type_key_stripped(self):
        """qdo's 'type' key is stripped before passing to Snowflake."""
        _, _, mock_connect = _make_connector(
            type="snowflake",
            account="x",
        )
        call_kwargs = mock_connect.call_args[1]
        assert "type" not in call_kwargs

    def test_extra_params_pass_through(self):
        """Warehouse, database, schema, role all pass through."""
        _, _, mock_connect = _make_connector(
            type="snowflake",
            account="x",
            user="u",
            warehouse="WH",
            database="DB",
            schema="SCH",
            role="ANALYST",
        )
        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["warehouse"] == "WH"
        assert call_kwargs["database"] == "DB"
        assert call_kwargs["schema"] == "SCH"
        assert call_kwargs["role"] == "ANALYST"

    def test_credential_caching_enabled_by_default(self):
        """SSO/MFA credential caching flags are on by default."""
        _, _, mock_connect = _make_connector(
            type="snowflake",
            account="x",
        )
        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["client_store_temporary_credential"] is True
        assert call_kwargs["client_request_mfa_token"] is True

    def test_credential_caching_can_be_disabled(self):
        """Users can explicitly disable credential caching."""
        _, _, mock_connect = _make_connector(
            type="snowflake",
            account="x",
            client_store_temporary_credential=False,
            client_request_mfa_token=False,
        )
        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["client_store_temporary_credential"] is False
        assert call_kwargs["client_request_mfa_token"] is False

    def test_close(self):
        connector, mock_conn, _ = _make_connector(type="snowflake", account="x")
        connector.close()
        mock_conn.close.assert_called_once()


# ---------------------------------------------------------------------------
# Arrow fetch tests
# ---------------------------------------------------------------------------


class TestSnowflakeArrow:
    def test_execute_uses_arrow(self):
        """execute() fetches via Arrow and returns list[dict]."""
        connector, mock_conn, _ = _make_connector(type="snowflake", account="x")

        batch = pa.RecordBatch.from_pydict(
            {
                "ID": [1, 2, 3],
                "NAME": ["Alice", "Bob", "Carol"],
                "SCORE": [95.5, 87.3, 92.1],
            }
        )
        cursor = _make_mock_cursor(
            arrow_batches=[pa.Table.from_batches([batch])],
            columns=["ID", "NAME", "SCORE"],
        )
        mock_conn.cursor.return_value = cursor

        result = connector.execute("SELECT * FROM scores")

        assert len(result) == 3
        assert result[0] == {"id": 1, "name": "Alice", "score": 95.5}
        assert result[2]["name"] == "Carol"
        cursor.fetch_arrow_batches.assert_called_once()

    def test_execute_arrow_returns_pyarrow_table(self):
        """execute_arrow() returns a PyArrow Table directly."""
        connector, mock_conn, _ = _make_connector(type="snowflake", account="x")

        batch = pa.RecordBatch.from_pydict(
            {
                "ID": [10, 20],
                "VALUE": [1.1, 2.2],
            }
        )
        cursor = _make_mock_cursor(
            arrow_batches=[pa.Table.from_batches([batch])],
            columns=["ID", "VALUE"],
        )
        mock_conn.cursor.return_value = cursor

        table = connector.execute_arrow("SELECT * FROM data")

        assert isinstance(table, pa.Table)
        assert table.num_rows == 2
        assert table.column_names == ["id", "value"]
        assert table.column("id").to_pylist() == [10, 20]

    def test_execute_arrow_multiple_batches(self):
        """execute_arrow() concatenates multiple Arrow batches."""
        connector, mock_conn, _ = _make_connector(type="snowflake", account="x")

        batch1 = pa.Table.from_pydict({"X": [1, 2]})
        batch2 = pa.Table.from_pydict({"X": [3, 4]})
        cursor = _make_mock_cursor(
            arrow_batches=[batch1, batch2],
            columns=["X"],
        )
        mock_conn.cursor.return_value = cursor

        table = connector.execute_arrow("SELECT x FROM big_table")

        assert table.num_rows == 4
        assert table.column("x").to_pylist() == [1, 2, 3, 4]

    def test_execute_arrow_empty_result(self):
        """execute_arrow() returns empty table when no rows."""
        connector, mock_conn, _ = _make_connector(type="snowflake", account="x")

        cursor = _make_mock_cursor(arrow_batches=[], columns=["A"])
        mock_conn.cursor.return_value = cursor

        table = connector.execute_arrow("SELECT a FROM empty")

        assert isinstance(table, pa.Table)
        assert table.num_rows == 0

    def test_execute_arrow_no_description(self):
        """execute_arrow() handles DDL/non-SELECT statements."""
        connector, mock_conn, _ = _make_connector(type="snowflake", account="x")

        cursor = _make_mock_cursor()  # description=None
        mock_conn.cursor.return_value = cursor

        table = connector.execute_arrow("CREATE TABLE foo (id INT)")

        assert isinstance(table, pa.Table)
        assert table.num_rows == 0

    def test_execute_arrow_preserves_types(self):
        """Arrow path preserves numeric types (int, float) without string coercion."""
        connector, mock_conn, _ = _make_connector(type="snowflake", account="x")

        batch = pa.RecordBatch.from_pydict(
            {
                "INT_COL": pa.array([1, 2, 3], type=pa.int64()),
                "FLOAT_COL": pa.array([1.5, 2.5, 3.5], type=pa.float64()),
                "STR_COL": pa.array(["a", "b", "c"], type=pa.string()),
            }
        )
        cursor = _make_mock_cursor(
            arrow_batches=[pa.Table.from_batches([batch])],
            columns=["INT_COL", "FLOAT_COL", "STR_COL"],
        )
        mock_conn.cursor.return_value = cursor

        result = connector.execute("SELECT * FROM typed")

        assert isinstance(result[0]["int_col"], int)
        assert isinstance(result[0]["float_col"], float)
        assert isinstance(result[0]["str_col"], str)

    def test_execute_falls_back_to_standard_fetch(self):
        """If Arrow fetch fails, execute() falls back to standard cursor."""
        connector, mock_conn, _ = _make_connector(type="snowflake", account="x")

        cursor = _make_mock_cursor(
            arrow_batches=None,  # triggers Exception
            rows=[(1, "Alice"), (2, "Bob")],
            columns=["ID", "NAME"],
        )
        mock_conn.cursor.return_value = cursor

        result = connector.execute("SELECT * FROM users")

        assert len(result) == 2
        assert result[0] == {"id": 1, "name": "Alice"}
        cursor.fetchall.assert_called_once()


# ---------------------------------------------------------------------------
# get_columns tests
# ---------------------------------------------------------------------------


class TestSnowflakeGetColumns:
    def test_get_columns(self):
        """get_columns() returns normalized column metadata."""
        connector, mock_conn, _ = _make_connector(type="snowflake", account="x")

        col_batch = pa.RecordBatch.from_pydict(
            {
                "COLUMN_NAME": ["ID", "NAME", "SCORE"],
                "DATA_TYPE": ["NUMBER", "VARCHAR", "FLOAT"],
                "IS_NULLABLE": ["NO", "YES", "YES"],
                "COLUMN_DEFAULT": [None, None, "0"],
                "COMMENT": [None, "User name", None],
            }
        )
        cursor = _make_mock_cursor(
            arrow_batches=[pa.Table.from_batches([col_batch])],
            columns=["COLUMN_NAME", "DATA_TYPE", "IS_NULLABLE", "COLUMN_DEFAULT", "COMMENT"],
        )
        mock_conn.cursor.return_value = cursor

        cols = connector.get_columns("scores")

        assert len(cols) == 3
        assert cols[0] == {
            "name": "ID",
            "type": "NUMBER",
            "nullable": False,
            "default": None,
            "primary_key": False,
            "comment": None,
        }
        assert cols[1]["nullable"] is True
        assert cols[2]["default"] == "0"


# ---------------------------------------------------------------------------
# _resolve_table tests
# ---------------------------------------------------------------------------


class TestResolveTable:
    def test_bare_table_name(self):
        """Plain table name uses connection defaults."""
        connector, _, _ = _make_connector(type="snowflake", account="x")
        db, schema, tbl = connector._resolve_table("orders")
        assert (db, schema, tbl) == ("TEST_DB", "PUBLIC", "ORDERS")

    def test_schema_qualified(self):
        """schema.table overrides the default schema."""
        connector, _, _ = _make_connector(type="snowflake", account="x")
        db, schema, tbl = connector._resolve_table("analytics.events")
        assert (db, schema, tbl) == ("TEST_DB", "ANALYTICS", "EVENTS")

    def test_fully_qualified(self):
        """database.schema.table overrides both defaults."""
        connector, _, _ = _make_connector(type="snowflake", account="x")
        db, schema, tbl = connector._resolve_table("other_db.staging.raw_data")
        assert (db, schema, tbl) == ("OTHER_DB", "STAGING", "RAW_DATA")

    def test_uppercases_all_parts(self):
        """All components are uppercased."""
        connector, _, _ = _make_connector(type="snowflake", account="x")
        db, schema, tbl = connector._resolve_table("myDb.mySchema.myTable")
        assert (db, schema, tbl) == ("MYDB", "MYSCHEMA", "MYTABLE")

    def test_too_many_parts_raises(self):
        """Four-part names are rejected."""
        connector, _, _ = _make_connector(type="snowflake", account="x")
        import pytest

        with pytest.raises(ValueError, match="Invalid table reference"):
            connector._resolve_table("a.b.c.d")

    def test_invalid_identifier_raises(self):
        """Components with unsafe characters are rejected."""
        connector, _, _ = _make_connector(type="snowflake", account="x")
        import pytest

        with pytest.raises(ValueError):
            connector._resolve_table("bad;drop")


class TestGetColumnsQualified:
    def test_get_columns_uses_qualified_parts(self):
        """get_columns with schema.table queries the right database and schema."""
        connector, mock_conn, _ = _make_connector(type="snowflake", account="x")

        col_batch = pa.RecordBatch.from_pydict(
            {
                "COLUMN_NAME": ["ID"],
                "DATA_TYPE": ["NUMBER"],
                "IS_NULLABLE": ["NO"],
                "COLUMN_DEFAULT": [None],
                "COMMENT": [None],
            }
        )
        cursor = _make_mock_cursor(
            arrow_batches=[pa.Table.from_batches([col_batch])],
            columns=["COLUMN_NAME", "DATA_TYPE", "IS_NULLABLE", "COLUMN_DEFAULT", "COMMENT"],
        )
        mock_conn.cursor.return_value = cursor

        connector.get_columns("analytics.events")

        # Verify the SQL used the correct database and the params used the
        # overridden schema.
        sql_arg = cursor.execute.call_args[0][0]
        assert "TEST_DB.information_schema.columns" in sql_arg
        params = cursor.execute.call_args[0][1]
        assert params == ("ANALYTICS", "EVENTS")

    def test_get_columns_fully_qualified(self):
        """get_columns with db.schema.table queries the specified database."""
        connector, mock_conn, _ = _make_connector(type="snowflake", account="x")

        col_batch = pa.RecordBatch.from_pydict(
            {
                "COLUMN_NAME": ["VAL"],
                "DATA_TYPE": ["FLOAT"],
                "IS_NULLABLE": ["YES"],
                "COLUMN_DEFAULT": [None],
                "COMMENT": [None],
            }
        )
        cursor = _make_mock_cursor(
            arrow_batches=[pa.Table.from_batches([col_batch])],
            columns=["COLUMN_NAME", "DATA_TYPE", "IS_NULLABLE", "COLUMN_DEFAULT", "COMMENT"],
        )
        mock_conn.cursor.return_value = cursor

        connector.get_columns("other_db.staging.metrics")

        sql_arg = cursor.execute.call_args[0][0]
        assert "OTHER_DB.information_schema.columns" in sql_arg
        params = cursor.execute.call_args[0][1]
        assert params == ("STAGING", "METRICS")


# ---------------------------------------------------------------------------
# Factory integration
# ---------------------------------------------------------------------------


class TestSnowflakeFactory:
    def test_factory_creates_snowflake_connector(self):
        """create_connector routes type='snowflake' correctly."""
        _mock_connect.reset_mock()
        mock_conn = MagicMock()
        init_cursor = MagicMock()
        init_cursor.fetchone.return_value = ("TEST_DB", "PUBLIC")
        mock_conn.cursor.return_value = init_cursor
        _mock_connect.return_value = mock_conn
        from querido.connectors.factory import create_connector

        config = {
            "type": "snowflake",
            "account": "test-acct",
            "user": "testuser",
            "auth": "externalbrowser",
        }
        connector = create_connector(config)

        assert connector.dialect == "snowflake"
        call_kwargs = _mock_connect.call_args[1]
        assert call_kwargs["account"] == "test-acct"
        assert call_kwargs["authenticator"] == "externalbrowser"


# ---------------------------------------------------------------------------
# SQL template tests
# ---------------------------------------------------------------------------


class TestSnowflakeTemplates:
    def test_profile_template_numeric_approx(self):
        """Default (approx) profile uses APPROX_COUNT_DISTINCT in a single SELECT."""
        from querido.sql.renderer import render_template

        cols = [{"name": "PRICE", "type": "FLOAT", "numeric": True}]
        sql = render_template("profile", "snowflake", columns=cols, source="products", approx=True)
        assert "AVG" in sql
        assert "APPROX_PERCENTILE" in sql
        assert "STDDEV" in sql
        assert "products" in sql
        assert "APPROX_COUNT_DISTINCT" in sql
        assert "COUNT(DISTINCT" not in sql
        # Single SELECT, no UNION ALL
        assert "UNION" not in sql

    def test_profile_template_numeric_exact(self):
        """Exact profile uses COUNT(DISTINCT) in a single SELECT."""
        from querido.sql.renderer import render_template

        cols = [{"name": "PRICE", "type": "FLOAT", "numeric": True}]
        sql = render_template(
            "profile", "snowflake", columns=cols, source="products", approx=False
        )
        assert "COUNT(DISTINCT" in sql
        assert "APPROX_COUNT_DISTINCT" not in sql
        assert "UNION" not in sql

    def test_profile_template_string(self):
        from querido.sql.renderer import render_template

        cols = [{"name": "EMAIL", "type": "VARCHAR", "numeric": False}]
        sql = render_template("profile", "snowflake", columns=cols, source="users", approx=True)
        assert "LENGTH" in sql
        assert "min_length" in sql
        assert "UNION" not in sql

    def test_profile_template_single_scan_multiple_cols(self):
        """Multiple columns produce a single SELECT with all stats."""
        from querido.sql.renderer import render_template

        cols = [
            {"name": "ID", "type": "NUMBER", "numeric": True},
            {"name": "NAME", "type": "VARCHAR", "numeric": False},
            {"name": "SCORE", "type": "FLOAT", "numeric": True},
        ]
        sql = render_template("profile", "snowflake", columns=cols, source="scores", approx=True)
        # Single SELECT — no UNION ALL
        assert "UNION" not in sql
        assert sql.strip().startswith("SELECT")
        # All columns present
        assert '"ID__null_count"' in sql
        assert '"NAME__min_length"' in sql
        assert '"SCORE__distinct_count"' in sql

    def test_preview_uses_common_template(self):
        from querido.sql.renderer import render_template

        sql = render_template("preview", "snowflake", table="ORDERS", limit=10)
        assert "ORDERS" in sql
        assert "10" in sql

    def test_preview_qualified_table(self):
        """Qualified table names work in FROM clauses."""
        from querido.sql.renderer import render_template

        sql = render_template("preview", "snowflake", table="MY_DB.STAGING.ORDERS", limit=10)
        assert "MY_DB.STAGING.ORDERS" in sql

    def test_scratch_uses_table_name_for_identifier(self):
        """Scratch template uses short table_name for tmp_ prefix, not full qualified name."""
        from querido.sql.renderer import render_template

        cols = [{"name": "ID", "type": "NUMBER", "nullable": False}]
        sql = render_template(
            "generate/scratch",
            "snowflake",
            table_name="ORDERS",
            columns=cols,
            rows=["1"],
        )
        assert "tmp_ORDERS" in sql
        assert "tmp_MY_DB" not in sql

    def test_task_uses_table_name_for_identifier(self):
        """Task template uses short table_name for task name, full table for FROM."""
        from querido.sql.renderer import render_template

        cols = [{"name": "ID", "type": "NUMBER"}]
        sql = render_template(
            "generate/task",
            "snowflake",
            table="MY_DB.STAGING.ORDERS",
            table_name="ORDERS",
            columns=cols,
        )
        assert "TASK ORDERS_task" in sql
        assert "FROM MY_DB.STAGING.ORDERS" in sql

    def test_procedure_uses_table_name_for_identifier(self):
        """Procedure template uses short table_name for proc name, full table for FROM."""
        from querido.sql.renderer import render_template

        cols = [{"name": "ID", "type": "NUMBER"}]
        sql = render_template(
            "generate/procedure",
            "snowflake",
            table="MY_DB.STAGING.ORDERS",
            table_name="ORDERS",
            columns=cols,
        )
        assert "process_orders()" in sql
        assert "FROM MY_DB.STAGING.ORDERS" in sql


# ---------------------------------------------------------------------------
# Sampling syntax
# ---------------------------------------------------------------------------


class TestSnowflakeSampling:
    def test_snowflake_sample_syntax(self):
        """Snowflake uses SAMPLE (n ROWS) syntax."""
        table = "big_table"
        sample_size = 100_000
        source = f"(SELECT * FROM {table} SAMPLE ({sample_size} ROWS)) AS _sample"
        assert "SAMPLE (100000 ROWS)" in source


# ---------------------------------------------------------------------------
# No-default database/schema (fully-qualified names only)
# ---------------------------------------------------------------------------


class TestNoDefaultDatabaseSchema:
    """Connectors without default database/schema should work with qualified names."""

    def test_init_succeeds_without_db_schema(self):
        """Connection should succeed even if session has no default db/schema."""
        connector, _, _ = _make_connector(
            type="snowflake", account="x", _session_db="", _session_schema=""
        )
        assert connector._database == ""
        assert connector._schema == ""

    def test_fully_qualified_resolves_without_defaults(self):
        """Fully-qualified names work even without connection defaults."""
        connector, _, _ = _make_connector(
            type="snowflake", account="x", _session_db="", _session_schema=""
        )
        db, schema, tbl = connector._resolve_table("my_db.my_schema.my_table")
        assert (db, schema, tbl) == ("MY_DB", "MY_SCHEMA", "MY_TABLE")

    def test_bare_name_fails_without_defaults(self):
        """Bare table name raises helpful error when defaults are missing."""
        import pytest

        connector, _, _ = _make_connector(
            type="snowflake", account="x", _session_db="", _session_schema=""
        )
        with pytest.raises(ValueError, match="Cannot resolve unqualified table name"):
            connector._resolve_table("orders")

    def test_schema_qualified_fails_without_database(self):
        """schema.table raises helpful error when database default is missing."""
        import pytest

        connector, _, _ = _make_connector(
            type="snowflake", account="x", _session_db="", _session_schema=""
        )
        with pytest.raises(ValueError, match="'database' not set"):
            connector._resolve_table("analytics.events")

    def test_schema_qualified_works_with_only_database(self):
        """schema.table works if only database is set (no default schema)."""
        connector, _, _ = _make_connector(
            type="snowflake", account="x", database="MY_DB", _session_db="", _session_schema=""
        )
        db, schema, tbl = connector._resolve_table("analytics.events")
        assert (db, schema, tbl) == ("MY_DB", "ANALYTICS", "EVENTS")

    def test_get_tables_fails_without_defaults(self):
        """get_tables() raises helpful error when defaults are missing."""
        import pytest

        connector, _, _ = _make_connector(
            type="snowflake", account="x", _session_db="", _session_schema=""
        )
        with pytest.raises(ValueError, match="Cannot list tables"):
            connector.get_tables()

    def test_get_tables_with_explicit_db_schema(self):
        """get_tables(database=..., schema=...) works without defaults."""
        connector, mock_conn, _ = _make_connector(
            type="snowflake", account="x", _session_db="", _session_schema=""
        )

        tbl_batch = pa.RecordBatch.from_pydict(
            {"TABLE_NAME": ["ORDERS"], "TABLE_TYPE": ["BASE TABLE"]}
        )
        cursor = _make_mock_cursor(
            arrow_batches=[pa.Table.from_batches([tbl_batch])],
            columns=["TABLE_NAME", "TABLE_TYPE"],
        )
        mock_conn.cursor.return_value = cursor

        tables = connector.get_tables(database="MY_DB", schema="PUBLIC")
        assert len(tables) == 1
        assert tables[0]["name"] == "ORDERS"

        sql_arg = cursor.execute.call_args[0][0]
        assert "MY_DB.information_schema.tables" in sql_arg


# ---------------------------------------------------------------------------
# check_table_exists with qualified Snowflake names
# ---------------------------------------------------------------------------


class TestCheckTableExistsQualified:
    """check_table_exists should resolve qualified names for Snowflake."""

    def test_qualified_name_matches(self):
        """Fully-qualified name should match when table exists in target schema."""
        connector, mock_conn, _ = _make_connector(type="snowflake", account="x")

        tbl_batch = pa.RecordBatch.from_pydict(
            {"TABLE_NAME": ["RAW_DATA", "METRICS"], "TABLE_TYPE": ["BASE TABLE", "BASE TABLE"]}
        )
        cursor = _make_mock_cursor(
            arrow_batches=[pa.Table.from_batches([tbl_batch])],
            columns=["TABLE_NAME", "TABLE_TYPE"],
        )
        mock_conn.cursor.return_value = cursor

        from querido.cli._util import check_table_exists

        # Should not raise
        check_table_exists(connector, "other_db.staging.raw_data")

        # Verify get_tables was called against the right database/schema
        sql_arg = cursor.execute.call_args[0][0]
        assert "OTHER_DB.information_schema.tables" in sql_arg
        params = cursor.execute.call_args[0][1]
        assert params == ("STAGING",)

    def test_qualified_name_not_found(self):
        """Fully-qualified name should raise when table does not exist."""
        import pytest
        import typer

        connector, mock_conn, _ = _make_connector(type="snowflake", account="x")

        tbl_batch = pa.RecordBatch.from_pydict(
            {"TABLE_NAME": ["OTHER_TABLE"], "TABLE_TYPE": ["BASE TABLE"]}
        )
        cursor = _make_mock_cursor(
            arrow_batches=[pa.Table.from_batches([tbl_batch])],
            columns=["TABLE_NAME", "TABLE_TYPE"],
        )
        mock_conn.cursor.return_value = cursor

        from querido.cli._util import check_table_exists

        with pytest.raises(typer.BadParameter, match="not found"):
            check_table_exists(connector, "other_db.staging.missing_table")

    def test_schema_qualified_name_matches(self):
        """Schema-qualified name should match when table exists."""
        connector, mock_conn, _ = _make_connector(type="snowflake", account="x")

        tbl_batch = pa.RecordBatch.from_pydict(
            {"TABLE_NAME": ["EVENTS"], "TABLE_TYPE": ["BASE TABLE"]}
        )
        cursor = _make_mock_cursor(
            arrow_batches=[pa.Table.from_batches([tbl_batch])],
            columns=["TABLE_NAME", "TABLE_TYPE"],
        )
        mock_conn.cursor.return_value = cursor

        from querido.cli._util import check_table_exists

        # Should not raise
        check_table_exists(connector, "analytics.events")


# ---------------------------------------------------------------------------
# _table_short_name helper
# ---------------------------------------------------------------------------


class TestTableShortName:
    def test_bare_name(self):
        from querido.cli.sql import _table_short_name

        assert _table_short_name("orders") == "orders"

    def test_schema_qualified(self):
        from querido.cli.sql import _table_short_name

        assert _table_short_name("analytics.events") == "events"

    def test_fully_qualified(self):
        from querido.cli.sql import _table_short_name

        assert _table_short_name("my_db.staging.raw_data") == "raw_data"


# ---------------------------------------------------------------------------
# Semantic YAML with qualified names
# ---------------------------------------------------------------------------


class TestSemanticYamlQualified:
    def test_semantic_yaml_uses_short_name(self):
        """Semantic model name uses just the table part, base_table keeps full ref."""
        from querido.cli.snowflake import _build_semantic_yaml

        columns = [{"name": "ID", "type": "NUMBER", "comment": None}]
        yaml_str = _build_semantic_yaml("MY_DB.STAGING.ORDERS", columns, None)
        assert "name: orders_semantic_model" in yaml_str
        assert "name: ORDERS" in yaml_str
        assert "base_table: MY_DB.STAGING.ORDERS" in yaml_str
        # Should NOT have dots in the model name
        assert "my_db.staging.orders_semantic_model" not in yaml_str
