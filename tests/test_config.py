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


def test_resolve_connection_as_path():
    config = resolve_connection("./data.db")
    assert config["type"] == "sqlite"
    assert config["path"] == "./data.db"


def test_resolve_connection_duckdb_extension():
    config = resolve_connection("./analytics.duckdb")
    assert config["type"] == "duckdb"


def test_resolve_connection_explicit_db_type():
    config = resolve_connection("./myfile.dat", db_type="duckdb")
    assert config["type"] == "duckdb"
