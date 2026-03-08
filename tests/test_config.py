import pytest

from querido.config import load_connections, resolve_connection


def test_load_connections_from_toml(tmp_path):
    config_file = tmp_path / "connections.toml"
    config_file.write_text('[connections.mydb]\ntype = "duckdb"\npath = "./analytics.duckdb"\n')
    connections = load_connections(tmp_path)
    assert "mydb" in connections
    assert connections["mydb"]["type"] == "duckdb"


def test_load_connections_missing_file(tmp_path):
    connections = load_connections(tmp_path)
    assert connections == {}


def test_resolve_connection_as_path(tmp_path):
    db_file = tmp_path / "data.db"
    db_file.touch()
    config = resolve_connection(str(db_file))
    assert config["type"] == "sqlite"
    assert config["path"] == str(db_file)


def test_resolve_connection_duckdb_extension(tmp_path):
    db_file = tmp_path / "analytics.duckdb"
    db_file.touch()
    config = resolve_connection(str(db_file))
    assert config["type"] == "duckdb"


def test_resolve_connection_explicit_db_type(tmp_path):
    db_file = tmp_path / "myfile.dat"
    db_file.touch()
    config = resolve_connection(str(db_file), db_type="duckdb")
    assert config["type"] == "duckdb"


def test_resolve_connection_missing_file_raises():
    with pytest.raises(FileNotFoundError, match="Database file not found"):
        resolve_connection("./nonexistent.db")


def test_resolve_connection_missing_file_suggests_config_add():
    with pytest.raises(FileNotFoundError, match="qdo config add"):
        resolve_connection("./nonexistent.db")
