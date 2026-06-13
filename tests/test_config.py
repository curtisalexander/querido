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
    with pytest.raises(FileNotFoundError, match="qdo config add --name <name>"):
        resolve_connection("./nonexistent.db")


def test_resolve_connection_mistyped_name_raises_connection_not_found(tmp_path, monkeypatch):
    from querido.config import ConnectionNotFoundError

    monkeypatch.setenv("QDO_CONFIG", str(tmp_path))
    (tmp_path / "connections.toml").write_text(
        '[connections.mydb]\ntype = "sqlite"\npath = "/tmp/test.db"\n'
    )
    with pytest.raises(ConnectionNotFoundError, match="Connection 'mydp' not found"):
        resolve_connection("mydp")


def test_resolve_connection_mistyped_name_lists_available(tmp_path, monkeypatch):
    from querido.config import ConnectionNotFoundError

    monkeypatch.setenv("QDO_CONFIG", str(tmp_path))
    (tmp_path / "connections.toml").write_text(
        '[connections.mydb]\ntype = "sqlite"\npath = "/tmp/test.db"\n'
    )
    with pytest.raises(ConnectionNotFoundError, match="Available connections: mydb"):
        resolve_connection("ghost")


def test_resolve_connection_expands_tilde_for_direct_path(tmp_path, monkeypatch):
    monkeypatch.setenv("QDO_CONFIG", str(tmp_path / "config"))
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # expanduser reads this on Windows
    (home / "data.db").touch()

    config = resolve_connection("~/data.db")
    assert config.get("type") == "sqlite"
    assert config.get("path") == str(home / "data.db")


def test_resolve_connection_expands_tilde_for_named_connection(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("QDO_CONFIG", str(config_dir))
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # expanduser reads this on Windows
    (config_dir / "connections.toml").write_text(
        '[connections.mydb]\ntype = "sqlite"\npath = "~/data.db"\n'
    )

    config = resolve_connection("mydb")
    assert config.get("path") == str(home / "data.db")


def test_resolve_connection_expands_tilde_for_parquet(tmp_path, monkeypatch):
    monkeypatch.setenv("QDO_CONFIG", str(tmp_path / "config"))
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # expanduser reads this on Windows

    config = resolve_connection("~/events.parquet")
    assert config.get("type") == "duckdb"
    assert config.get("parquet_path") == str(home / "events.parquet")


# ---------------------------------------------------------------------------
# Column sets — dotted table names and legacy-format migration
# ---------------------------------------------------------------------------


def test_column_set_round_trip_dotted_table(tmp_path):
    from querido.config import (
        delete_column_set,
        list_column_sets,
        load_column_set,
        save_column_set,
    )

    save_column_set("snow", "db.schema.tbl", "wide", ["a", "b", "c"], tmp_path)
    assert load_column_set("snow", "db.schema.tbl", "wide", tmp_path) == ["a", "b", "c"]

    # Table-filtered listing must match the full dotted table name
    sets = list_column_sets(table="db.schema.tbl", config_dir=tmp_path)
    assert len(sets) == 1
    entry = sets[0]
    assert entry.get("connection") == "snow"
    assert entry.get("table") == "db.schema.tbl"
    assert entry.get("set") == "wide"
    assert entry.get("columns") == ["a", "b", "c"]

    # No false positives on a prefix segment of the dotted name
    assert list_column_sets(table="db", config_dir=tmp_path) == []

    assert delete_column_set("snow", "db.schema.tbl", "wide", tmp_path) is True
    assert load_column_set("snow", "db.schema.tbl", "wide", tmp_path) is None


def test_column_set_legacy_format_read_best_effort(tmp_path):
    """Legacy dot-joined keys are still readable (first=connection, last=set)."""
    from querido.config import list_column_sets, load_column_set

    (tmp_path / "column_sets.toml").write_text(
        '["snow.db.schema.tbl.wide"]\ncolumns = ["a", "b"]\n'
        '["conn1.orders.default"]\ncolumns = ["id"]\n'
    )

    assert load_column_set("snow", "db.schema.tbl", "wide", tmp_path) == ["a", "b"]
    assert load_column_set("conn1", "orders", "default", tmp_path) == ["id"]

    sets = list_column_sets(connection="snow", table="db.schema.tbl", config_dir=tmp_path)
    assert len(sets) == 1
    assert sets[0].get("set") == "wide"


def test_column_set_legacy_format_migrated_on_write(tmp_path):
    """Saving rewrites legacy entries into the structured [[sets]] format."""
    from querido.config import load_column_set, save_column_set

    (tmp_path / "column_sets.toml").write_text('["conn1.orders.default"]\ncolumns = ["id"]\n')

    save_column_set("conn2", "users", "names", ["name"], tmp_path)

    content = (tmp_path / "column_sets.toml").read_text()
    assert "[[sets]]" in content
    assert "conn1.orders.default" not in content
    # The legacy entry survives migration
    assert load_column_set("conn1", "orders", "default", tmp_path) == ["id"]
    assert load_column_set("conn2", "users", "names", tmp_path) == ["name"]
