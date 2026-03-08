"""Tests for the qdo web UI (FastAPI TestClient, no real server)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_web_path(tmp_path: Path) -> str:
    """SQLite DB with tables and a view for web UI testing."""
    db_path = str(tmp_path / "web_test.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, age INTEGER, city TEXT)"
    )
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 30, 'NYC')")
    conn.execute("INSERT INTO users VALUES (2, 'Bob', 25, 'LA')")
    conn.execute("INSERT INTO users VALUES (3, 'Charlie', 35, 'NYC')")
    conn.execute(
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL, status TEXT)"
    )
    conn.execute("INSERT INTO orders VALUES (1, 1, 99.99, 'shipped')")
    conn.execute("INSERT INTO orders VALUES (2, 2, 49.50, 'pending')")
    conn.execute("INSERT INTO orders VALUES (3, 1, 25.00, 'shipped')")
    conn.execute("CREATE VIEW active_users AS SELECT * FROM users WHERE age > 20")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def web_client(sqlite_web_path: str):
    """FastAPI TestClient with a real SQLite connector."""
    from querido.connectors.sqlite import SQLiteConnector
    from querido.web import create_app

    connector = SQLiteConnector(sqlite_web_path, check_same_thread=False)
    app = create_app(connector, "test-connection")

    from starlette.testclient import TestClient

    with TestClient(app) as client:
        yield client
    connector.close()


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------


class TestLandingPage:
    def test_landing_returns_200(self, web_client):
        resp = web_client.get("/")
        assert resp.status_code == 200

    def test_landing_contains_tables(self, web_client):
        resp = web_client.get("/")
        body = resp.text
        assert "users" in body
        assert "orders" in body
        assert "active_users" in body

    def test_landing_contains_connection_name(self, web_client):
        resp = web_client.get("/")
        assert "test-connection" in resp.text


# ---------------------------------------------------------------------------
# Table detail page
# ---------------------------------------------------------------------------


class TestTableDetail:
    def test_table_page_returns_200(self, web_client):
        resp = web_client.get("/table/users")
        assert resp.status_code == 200

    def test_table_page_has_tabs(self, web_client):
        resp = web_client.get("/table/users")
        body = resp.text
        assert "Inspect" in body
        assert "Preview" in body
        assert "Profile" in body
        assert "Template" in body
        assert "Pivot" in body

    def test_view_page_has_lineage_tab(self, web_client):
        resp = web_client.get("/table/active_users")
        assert "Lineage" in resp.text

    def test_table_page_rejects_invalid_name(self, web_client):
        resp = web_client.get("/table/drop%20table")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Fragment endpoints
# ---------------------------------------------------------------------------


class TestInspectFragment:
    def test_inspect_returns_200(self, web_client):
        resp = web_client.get("/fragments/inspect/users")
        assert resp.status_code == 200

    def test_inspect_contains_columns(self, web_client):
        resp = web_client.get("/fragments/inspect/users")
        body = resp.text
        assert "name" in body
        assert "age" in body
        assert "city" in body


class TestPreviewFragment:
    def test_preview_returns_200(self, web_client):
        resp = web_client.get("/fragments/preview/users")
        assert resp.status_code == 200

    def test_preview_contains_data(self, web_client):
        resp = web_client.get("/fragments/preview/users")
        body = resp.text
        assert "Alice" in body
        assert "Bob" in body

    def test_preview_respects_limit(self, web_client):
        resp = web_client.get("/fragments/preview/users?limit=1")
        assert resp.status_code == 200


class TestProfileFragment:
    def test_profile_returns_200(self, web_client):
        resp = web_client.get("/fragments/profile/users")
        assert resp.status_code == 200

    def test_profile_contains_stats(self, web_client):
        resp = web_client.get("/fragments/profile/users")
        body = resp.text
        # Should have column names in the profile output
        assert "name" in body or "age" in body


class TestDistFragment:
    def test_dist_returns_200(self, web_client):
        resp = web_client.get("/fragments/dist/users/age")
        assert resp.status_code == 200

    def test_dist_contains_distribution(self, web_client):
        resp = web_client.get("/fragments/dist/users/city")
        body = resp.text
        assert "NYC" in body or "categorical" in body


class TestTemplateFragment:
    def test_template_returns_200(self, web_client):
        resp = web_client.get("/fragments/template/users")
        assert resp.status_code == 200

    def test_template_contains_columns(self, web_client):
        resp = web_client.get("/fragments/template/users")
        assert "name" in resp.text


class TestLineageFragment:
    def test_lineage_returns_200_for_view(self, web_client):
        resp = web_client.get("/fragments/lineage/active_users")
        assert resp.status_code == 200
        assert "SELECT" in resp.text

    def test_lineage_returns_message_for_table(self, web_client):
        resp = web_client.get("/fragments/lineage/users")
        assert resp.status_code == 200
        assert "Not a view" in resp.text


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_search_returns_all_when_empty(self, web_client):
        resp = web_client.get("/fragments/search?q=")
        assert resp.status_code == 200
        assert "users" in resp.text

    def test_search_filters_results(self, web_client):
        resp = web_client.get("/fragments/search?q=order")
        assert resp.status_code == 200
        assert "orders" in resp.text


# ---------------------------------------------------------------------------
# Pivot
# ---------------------------------------------------------------------------


class TestPivot:
    def test_pivot_page_returns_200(self, web_client):
        resp = web_client.get("/table/users/pivot")
        assert resp.status_code == 200
        assert "Group by" in resp.text

    def test_pivot_result(self, web_client):
        resp = web_client.post(
            "/fragments/pivot/users",
            data={"rows": ["city"], "values": ["age"], "agg": "COUNT"},
        )
        assert resp.status_code == 200
        assert "NYC" in resp.text or "count_age" in resp.text

    def test_pivot_invalid_agg(self, web_client):
        resp = web_client.post(
            "/fragments/pivot/users",
            data={"rows": ["city"], "values": ["age"], "agg": "INVALID"},
        )
        assert resp.status_code == 200
        assert "Invalid aggregation" in resp.text


# ---------------------------------------------------------------------------
# Pivot query builder (unit)
# ---------------------------------------------------------------------------


class TestPivotQueryBuilder:
    def test_build_pivot_query(self):
        from querido.core.pivot import build_pivot_query

        sql = build_pivot_query("users", ["city"], ["age"], "COUNT")
        assert "GROUP BY city" in sql
        assert "COUNT(age)" in sql

    def test_build_pivot_query_multi_cols(self):
        from querido.core.pivot import build_pivot_query

        sql = build_pivot_query("orders", ["status", "user_id"], ["amount"], "SUM")
        assert "GROUP BY status, user_id" in sql
        assert "SUM(amount)" in sql
