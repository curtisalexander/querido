"""Tests for qdo sql — SQL statement generation."""

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


class TestSqlSelect:
    def test_select_sqlite(self, sqlite_path: str) -> None:
        result = runner.invoke(app, ["sql", "select", "-t", "users", "-c", sqlite_path])
        assert result.exit_code == 0
        assert "SELECT" in result.output
        assert "id," in result.output
        assert "name," in result.output
        assert "age" in result.output
        assert "FROM users;" in result.output

    def test_select_duckdb(self, duckdb_path: str) -> None:
        result = runner.invoke(app, ["sql", "select", "-t", "users", "-c", duckdb_path])
        assert result.exit_code == 0
        assert "SELECT" in result.output
        assert "FROM users;" in result.output


class TestSqlInsert:
    def test_insert_sqlite(self, sqlite_path: str) -> None:
        result = runner.invoke(app, ["sql", "insert", "-t", "users", "-c", sqlite_path])
        assert result.exit_code == 0
        assert "INSERT INTO users" in result.output
        assert ":id," in result.output
        assert ":name," in result.output
        assert ":age" in result.output
        assert "VALUES" in result.output


class TestSqlDdl:
    def test_ddl_sqlite(self, sqlite_path: str) -> None:
        result = runner.invoke(app, ["sql", "ddl", "-t", "users", "-c", sqlite_path])
        assert result.exit_code == 0
        assert "CREATE TABLE users" in result.output
        assert "id INTEGER" in result.output
        assert "PRIMARY KEY" in result.output
        assert "name TEXT NOT NULL" in result.output

    def test_ddl_duckdb(self, duckdb_path: str) -> None:
        result = runner.invoke(app, ["sql", "ddl", "-t", "users", "-c", duckdb_path])
        assert result.exit_code == 0
        assert "CREATE TABLE users" in result.output
        assert "id INTEGER" in result.output
        assert "name VARCHAR NOT NULL" in result.output


class TestSqlUdf:
    def test_udf_sqlite(self, sqlite_path: str) -> None:
        result = runner.invoke(app, ["sql", "udf", "-t", "users", "-c", sqlite_path])
        assert result.exit_code == 0
        assert "create_function" in result.output
        assert "my_udf" in result.output
        assert "def my_udf(" in result.output

    def test_udf_duckdb(self, duckdb_path: str) -> None:
        result = runner.invoke(app, ["sql", "udf", "-t", "users", "-c", duckdb_path])
        assert result.exit_code == 0
        assert "CREATE OR REPLACE FUNCTION my_udf" in result.output
        assert "RETURNS VARCHAR" in result.output
        assert "LANGUAGE SQL" in result.output


class TestSqlSnowflakeOnly:
    def test_task_rejects_sqlite(self, sqlite_path: str) -> None:
        result = runner.invoke(app, ["sql", "task", "-t", "users", "-c", sqlite_path])
        assert result.exit_code != 0
        assert "Snowflake" in result.output

    def test_procedure_rejects_duckdb(self, duckdb_path: str) -> None:
        result = runner.invoke(app, ["sql", "procedure", "-t", "users", "-c", duckdb_path])
        assert result.exit_code != 0
        assert "Snowflake" in result.output


class TestSqlScratch:
    def test_scratch_sqlite(self, sqlite_path: str) -> None:
        result = runner.invoke(
            app, ["sql", "scratch", "-t", "users", "-c", sqlite_path, "-r", "2"]
        )
        assert result.exit_code == 0
        assert "CREATE TEMP TABLE tmp_users" in result.output
        assert "INSERT INTO tmp_users" in result.output
        assert "'Alice'" in result.output
        assert "'Bob'" in result.output
        assert "SELECT * FROM tmp_users" in result.output

    def test_scratch_duckdb(self, duckdb_path: str) -> None:
        result = runner.invoke(
            app, ["sql", "scratch", "-t", "users", "-c", duckdb_path, "-r", "1"]
        )
        assert result.exit_code == 0
        assert "CREATE TEMP TABLE tmp_users" in result.output
        assert "INSERT INTO tmp_users" in result.output
        # Only 1 row requested
        assert result.output.count("INSERT INTO") == 1

    def test_scratch_null_handling(self, sqlite_path: str) -> None:
        """NULL values render as SQL NULL, not Python None."""
        result = runner.invoke(app, ["sql", "scratch", "-t", "users", "-c", sqlite_path])
        assert result.exit_code == 0
        # age column is nullable and has values, but verify NULL literal isn't 'None'
        assert "None" not in result.output


class TestSqlHelp:
    def test_sql_help(self) -> None:
        result = runner.invoke(app, ["sql", "--help"])
        assert result.exit_code == 0
        assert "select" in result.output
        assert "insert" in result.output
        assert "ddl" in result.output
        assert "task" in result.output
        assert "udf" in result.output
        assert "procedure" in result.output
        assert "scratch" in result.output
