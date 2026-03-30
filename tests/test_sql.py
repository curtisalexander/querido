import sqlite3
from pathlib import Path

import pytest
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

    def test_select_has_all_columns_with_commas(self, sqlite_path: str) -> None:
        result = runner.invoke(app, ["sql", "select", "-t", "users", "-c", sqlite_path])
        assert result.exit_code == 0
        output = result.output
        assert "id" in output
        assert "name" in output
        assert "age" in output
        # Last column should not have trailing comma before FROM
        lines = output.strip().splitlines()
        from_idx = next(i for i, line in enumerate(lines) if "FROM" in line)
        col_line = lines[from_idx - 1].strip()
        assert not col_line.endswith(",")


class TestSqlInsert:
    def test_insert_sqlite(self, sqlite_path: str) -> None:
        result = runner.invoke(app, ["sql", "insert", "-t", "users", "-c", sqlite_path])
        assert result.exit_code == 0
        assert "INSERT INTO users" in result.output
        assert ":id," in result.output
        assert ":name," in result.output
        assert ":age" in result.output
        assert "VALUES" in result.output

    def test_insert_correct_placeholder_count(self, sqlite_path: str) -> None:
        result = runner.invoke(app, ["sql", "insert", "-t", "users", "-c", sqlite_path])
        assert result.exit_code == 0
        output = result.output
        # 3 columns: id, name, age => 3 placeholders
        assert output.count(":id") >= 1
        assert output.count(":name") >= 1
        assert output.count(":age") >= 1


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

    def test_ddl_not_null_constraints(self, sqlite_path: str) -> None:
        result = runner.invoke(app, ["sql", "ddl", "-t", "users", "-c", sqlite_path])
        assert result.exit_code == 0
        assert "NOT NULL" in result.output
        # 'age' is nullable, so it should not have NOT NULL
        for line in result.output.splitlines():
            if "age" in line and "INTEGER" in line:
                assert "NOT NULL" not in line


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
        assert result.output.count("INSERT INTO") == 1

    def test_scratch_null_handling(self, sqlite_path: str) -> None:
        result = runner.invoke(app, ["sql", "scratch", "-t", "users", "-c", sqlite_path])
        assert result.exit_code == 0
        assert "None" not in result.output

    def test_scratch_rows_1(self, sqlite_path: str) -> None:
        result = runner.invoke(
            app, ["sql", "scratch", "-t", "users", "-c", sqlite_path, "-r", "1"]
        )
        assert result.exit_code == 0
        assert result.output.count("INSERT INTO") == 1

    def test_scratch_rows_0_rejected(self, sqlite_path: str) -> None:
        result = runner.invoke(
            app, ["sql", "scratch", "-t", "users", "-c", sqlite_path, "-r", "0"]
        )
        assert result.exit_code != 0

    def test_scratch_generates_executable_sql(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "scratch_exec.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, label TEXT)")
        conn.execute("INSERT INTO items VALUES (1, 'hello')")
        conn.execute("INSERT INTO items VALUES (2, 'world')")
        conn.commit()
        conn.close()

        result = runner.invoke(app, ["sql", "scratch", "-t", "items", "-c", db_path, "-r", "2"])
        assert result.exit_code == 0

        # The generated SQL should be executable against a fresh database
        verify_conn = sqlite3.connect(":memory:")
        # Execute line by line (split on semicolons for multi-statement)
        sql = result.output.strip()
        # Remove comment lines
        statements = []
        current = []
        for line in sql.splitlines():
            stripped = line.strip()
            if stripped.startswith("--"):
                continue
            current.append(line)
            if stripped.endswith(";"):
                statements.append("\n".join(current))
                current = []

        for stmt in statements:
            stmt = stmt.strip()
            if stmt:
                verify_conn.execute(stmt)

        rows = verify_conn.execute("SELECT * FROM tmp_items").fetchall()
        assert len(rows) == 2
        verify_conn.close()


class TestSqlEmptyTable:
    @pytest.fixture
    def empty_sqlite(self, tmp_path: Path) -> str:
        db_path = str(tmp_path / "empty.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE empty_t (id INTEGER PRIMARY KEY, name TEXT NOT NULL, score REAL)"
        )
        conn.commit()
        conn.close()
        return db_path

    def test_select_empty_table(self, empty_sqlite: str) -> None:
        result = runner.invoke(app, ["sql", "select", "-c", empty_sqlite, "-t", "empty_t"])
        assert result.exit_code == 0
        assert "SELECT" in result.output
        assert "FROM empty_t;" in result.output

    def test_ddl_empty_table(self, empty_sqlite: str) -> None:
        result = runner.invoke(app, ["sql", "ddl", "-c", empty_sqlite, "-t", "empty_t"])
        assert result.exit_code == 0
        assert "CREATE TABLE empty_t" in result.output

    def test_insert_empty_table(self, empty_sqlite: str) -> None:
        result = runner.invoke(app, ["sql", "insert", "-c", empty_sqlite, "-t", "empty_t"])
        assert result.exit_code == 0
        assert "INSERT INTO empty_t" in result.output


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
