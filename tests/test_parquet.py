from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def _create_parquet(tmp_path):
    """Create a test parquet file and return its path."""
    import duckdb

    parquet_path = str(tmp_path / "sales.parquet")
    conn = duckdb.connect(":memory:")
    conn.execute(
        "CREATE TABLE sales AS SELECT * FROM VALUES "
        "(1, 'Widget', 9.99, 'Alice'), "
        "(2, 'Gadget', 19.99, 'Bob'), "
        "(3, 'Widget', 9.99, 'Alice') "
        "t(id, product, price, seller)"
    )
    conn.execute(f"COPY sales TO '{parquet_path}' (FORMAT PARQUET)")
    conn.close()
    return parquet_path


def test_inspect_parquet(tmp_path):
    parquet_path = _create_parquet(tmp_path)
    result = runner.invoke(app, ["inspect", "-c", parquet_path, "-t", "sales"])
    assert result.exit_code == 0
    assert "id" in result.output
    assert "product" in result.output
    assert "price" in result.output


def test_preview_parquet(tmp_path):
    parquet_path = _create_parquet(tmp_path)
    result = runner.invoke(app, ["preview", "-c", parquet_path, "-t", "sales"])
    assert result.exit_code == 0
    assert "Widget" in result.output
    assert "Gadget" in result.output


def test_profile_parquet(tmp_path):
    parquet_path = _create_parquet(tmp_path)
    result = runner.invoke(app, ["profile", "-c", parquet_path, "-t", "sales"])
    assert result.exit_code == 0
    assert "Numeric Columns" in result.output
    assert "String Columns" in result.output


def test_profile_parquet_top_values(tmp_path):
    parquet_path = _create_parquet(tmp_path)
    result = runner.invoke(app, ["profile", "-c", parquet_path, "-t", "sales", "--top", "3"])
    assert result.exit_code == 0
    assert "Top values" in result.output
    assert "Widget" in result.output
