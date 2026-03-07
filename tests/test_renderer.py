from querido.sql.renderer import render_template


def test_render_common_template():
    sql = render_template("test", "sqlite", table="users", limit=10)
    assert "SELECT * FROM users LIMIT 10" in sql


def test_render_falls_back_to_common():
    sql = render_template("test", "duckdb", table="orders", limit=5)
    assert "SELECT * FROM orders LIMIT 5" in sql
