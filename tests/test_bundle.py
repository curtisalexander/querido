"""Tests for ``qdo bundle`` (Phase 3.1: knowledge bundles)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from querido.cli.main import app
from querido.core.bundle import (
    compute_schema_fingerprint,
    diff_bundles,
    inspect_bundle,
)
from querido.core.bundle import (
    export_bundle as _export_bundle,
)
from querido.core.bundle import (
    import_bundle as _import_bundle,
)

runner = CliRunner()


def export_bundle(
    connection: str,
    tables: list[str],
    output: str | Path,
    *,
    include_column_sets: bool = True,
    **kwargs,
) -> dict:
    """Compose the internal bundle operation as the CLI application layer does."""
    from querido.config import list_column_sets, resolve_connection
    from querido.connectors.factory import create_connector

    column_sets = list_column_sets(connection=connection) if include_column_sets else []
    with create_connector(resolve_connection(connection)) as connector:
        return _export_bundle(
            connection,
            connector,
            tables,
            output,
            column_sets=column_sets,
            **kwargs,
        )


def import_bundle(
    bundle: str | Path,
    target: str,
    *,
    apply: bool = False,
    **kwargs,
) -> dict:
    """Compose import and persistence as the CLI application layer does."""
    from querido.config import resolve_connection, save_column_set
    from querido.connectors.factory import create_connector

    with create_connector(resolve_connection(target)) as connector:
        report = _import_bundle(bundle, target, connector, apply=apply, **kwargs)
    if apply:
        for entry in report["column_sets"]:
            name = entry.get("name")
            if name:
                save_column_set(target, entry["target_table"], name, entry["columns"])
                entry["applied"] = True
    return report


# -- schema fingerprint ------------------------------------------------------


def test_fingerprint_is_stable_and_order_independent():
    cols_a = [{"name": "id", "type": "INTEGER"}, {"name": "name", "type": "VARCHAR(255)"}]
    cols_b = [{"name": "NAME", "type": "varchar"}, {"name": "ID", "type": "integer"}]
    assert compute_schema_fingerprint(cols_a) == compute_schema_fingerprint(cols_b)


def test_fingerprint_changes_with_type():
    cols_a = [{"name": "id", "type": "INTEGER"}]
    cols_b = [{"name": "id", "type": "BIGINT"}]
    assert compute_schema_fingerprint(cols_a) != compute_schema_fingerprint(cols_b)


# -- export / inspect round trip --------------------------------------------


def _seed_metadata(
    connection: str,
    table: str,
    *,
    table_description: str = "users of the system",
    col_description: str | dict = "full legal name",
    extra_col_fields: dict | None = None,
    notes: str = "",
) -> Path:
    """Write a metadata YAML for *table* under .qdo/metadata/<conn>/."""
    from querido.core.metadata import metadata_path

    path = metadata_path(connection, table)
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        {"name": "id", "type": "INTEGER", "nullable": False, "primary_key": True},
        {
            "name": "name",
            "type": "TEXT",
            "nullable": False,
            "primary_key": False,
            "description": col_description,
        },
        {"name": "age", "type": "INTEGER", "nullable": True, "primary_key": False},
    ]
    if extra_col_fields:
        cols[1].update(extra_col_fields)
    meta = {
        "table": table,
        "connection": connection,
        "row_count": 2,
        "table_comment": "",
        "table_description": table_description,
        "data_owner": "platform-team",
        "update_frequency": "daily",
        "notes": notes,
        "columns": cols,
    }
    path.write_text(yaml.safe_dump(meta, sort_keys=False))
    return path


def test_export_and_inspect_directory(sqlite_path: str, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_metadata(sqlite_path, "users")

    out = tmp_path / "users.qdobundle"
    manifest = export_bundle(sqlite_path, ["users"], out, include_column_sets=False)
    assert out.is_dir()
    assert (out / "manifest.yaml").exists()
    assert (out / "metadata" / "users.yaml").exists()
    assert len(manifest["tables"]) == 1
    assert manifest["tables"][0]["name"] == "users"
    assert manifest["tables"][0]["schema_fingerprint"]

    report = inspect_bundle(out)
    assert report["metadata_count"] == 1
    assert "users" in report["tables"]


def test_export_zip(sqlite_path: str, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_metadata(sqlite_path, "users")

    out = tmp_path / "users.zip"
    export_bundle(sqlite_path, ["users"], out, include_column_sets=False, as_zip=True)
    assert out.is_file()

    report = inspect_bundle(out)
    assert report["metadata_count"] == 1


def test_bundle_zip_rejects_parent_path(tmp_path: Path) -> None:
    """Archive extraction must not write outside its temporary directory."""
    archive = tmp_path / "unsafe.zip"
    escaped = tmp_path / "escaped.txt"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../../escaped.txt", "not allowed")

    with pytest.raises(ValueError):
        inspect_bundle(archive)
    assert not escaped.exists()


def test_bundle_zip_rejects_excessive_expanded_size(tmp_path: Path, monkeypatch) -> None:
    """Declared uncompressed sizes must be bounded before extraction."""
    from querido.core import bundle

    archive = tmp_path / "oversized.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.yaml", "format_version: 1\n")

    monkeypatch.setattr(bundle, "_MAX_ARCHIVE_BYTES", 1)
    with pytest.raises(ValueError):
        inspect_bundle(archive)


def test_bundle_zip_rejects_excessive_member_count(tmp_path: Path, monkeypatch) -> None:
    """Member counts are bounded independently of expanded byte size."""
    from querido.core import bundle

    archive = tmp_path / "too-many.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("manifest.yaml", "format_version: 1\n")
        zf.writestr("metadata/users.yaml", "table: users\n")

    monkeypatch.setattr(bundle, "_MAX_ARCHIVE_MEMBERS", 1)
    with pytest.raises(ValueError):
        inspect_bundle(archive)


def _setup_named_conn(tmp_path: Path, monkeypatch, name: str, db_path: str) -> None:
    """Register a named sqlite connection pointing at *db_path*.

    Writes the path as a TOML *literal* string (single-quoted) so Windows
    backslashes survive round-tripping — basic strings interpret ``\\U``
    sequences as Unicode escapes and fail to parse drive-letter paths.
    """
    cfg_dir = tmp_path / f"qdo-config-{name}"
    cfg_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("QDO_CONFIG", str(cfg_dir))
    (cfg_dir / "connections.toml").write_text(
        f"[connections.{name}]\ntype = \"sqlite\"\npath = '{db_path}'\n"
    )


def test_export_includes_column_sets(sqlite_path: str, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _setup_named_conn(tmp_path, monkeypatch, "src", sqlite_path)
    _seed_metadata("src", "users")

    from querido.config import save_column_set

    save_column_set("src", "users", "default", ["id", "name"])

    out = tmp_path / "users.qdobundle"
    manifest = export_bundle("src", ["users"], out)
    assert (out / "column-sets" / "users.default.yaml").exists()
    assert any(s["name"] == "default" for s in manifest["column_sets"])


def test_export_column_sets_not_misattributed_for_dotted_tables(
    sqlite_path: str, tmp_path: Path, monkeypatch
):
    """A set saved for a dotted table name must not leak into a prefix table's export."""
    monkeypatch.chdir(tmp_path)
    _setup_named_conn(tmp_path, monkeypatch, "src", sqlite_path)
    _seed_metadata("src", "users")

    from querido.config import save_column_set

    save_column_set("src", "users", "default", ["id", "name"])
    # Dotted table that shares the "users" prefix — must be excluded from a
    # bundle exporting only "users", not misparsed as table "users".
    save_column_set("src", "users.archive", "wide", ["id", "name", "email"])

    out = tmp_path / "users.qdobundle"
    manifest = export_bundle("src", ["users"], out)
    entries = manifest["column_sets"]
    assert [(e["table"], e["name"]) for e in entries] == [("users", "default")]


def test_export_redact_drops_sample_values_for_pii(sqlite_path: str, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_metadata(
        sqlite_path,
        "users",
        extra_col_fields={"pii": True, "sample_values": "Alice, Bob", "valid_values": ["a", "b"]},
    )

    out = tmp_path / "users.qdobundle"
    export_bundle(sqlite_path, ["users"], out, redact=True, include_column_sets=False)
    meta = yaml.safe_load((out / "metadata" / "users.yaml").read_text())
    name_col = next(c for c in meta["columns"] if c["name"] == "name")
    assert "sample_values" not in name_col
    assert "valid_values" not in name_col


# -- import --------------------------------------------------------------------


def test_import_into_fresh_connection_writes_metadata(
    sqlite_path: str, tmp_path: Path, monkeypatch, make_sqlite_db
):
    monkeypatch.chdir(tmp_path)
    _seed_metadata(sqlite_path, "users", table_description="exported desc")

    out = tmp_path / "src.qdobundle"
    export_bundle(sqlite_path, ["users"], out, include_column_sets=False)

    # Create a second identical SQLite DB to import into.

    other = make_sqlite_db(str(tmp_path / "other.db"))

    report = import_bundle(out, other, apply=True)
    assert report["tables"][0]["fingerprint_status"] == "match"
    assert report["tables"][0]["applied"] is True

    from querido.core.metadata import show_metadata

    imported = show_metadata(other, "users")
    assert imported is not None
    assert imported["table_description"] == "exported desc"


def test_import_refuses_newer_format_version(
    sqlite_path: str, tmp_path: Path, monkeypatch, make_sqlite_db
):
    # Failure mode: a bundle written by a future qdo (format_version 2+) was
    # imported as if it were format 1, silently misreading its contents. The
    # importer must refuse and tell the user to upgrade.
    monkeypatch.chdir(tmp_path)
    _seed_metadata(sqlite_path, "users")
    out = tmp_path / "src.qdobundle"
    export_bundle(sqlite_path, ["users"], out, include_column_sets=False)

    manifest_path = out / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["format_version"] = "99"
    manifest_path.write_text(yaml.safe_dump(manifest))

    other = make_sqlite_db(str(tmp_path / "other.db"))
    with pytest.raises(ValueError, match="format_version 99"):
        import_bundle(out, other, apply=False)


@pytest.mark.parametrize("operation", ["inspect", "diff"])
def test_bundle_readers_refuse_newer_format_version(
    sqlite_path: str, tmp_path: Path, monkeypatch, operation: str
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_metadata(sqlite_path, "users")
    out = tmp_path / "future.qdobundle"
    export_bundle(sqlite_path, ["users"], out, include_column_sets=False)

    manifest_path = out / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["format_version"] = "99"
    manifest_path.write_text(yaml.safe_dump(manifest))

    with pytest.raises(ValueError, match="format_version 99"):
        if operation == "inspect":
            inspect_bundle(out)
        else:
            diff_bundles(out, out)


def test_bundle_inspect_rejects_malformed_manifest(tmp_path: Path) -> None:
    bundle = tmp_path / "malformed.qdobundle"
    bundle.mkdir()
    (bundle / "manifest.yaml").write_text("format_version: 1\ntables: not-a-list\n")

    with pytest.raises(ValueError, match="'tables' must be a list"):
        inspect_bundle(bundle)


def test_import_dry_run_does_not_write(
    sqlite_path: str, tmp_path: Path, monkeypatch, make_sqlite_db
):
    monkeypatch.chdir(tmp_path)
    _seed_metadata(sqlite_path, "users")
    out = tmp_path / "src.qdobundle"
    export_bundle(sqlite_path, ["users"], out, include_column_sets=False)

    other = make_sqlite_db(str(tmp_path / "other.db"))

    report = import_bundle(out, other, apply=False)
    assert report["tables"][0]["field_actions"]
    assert report["tables"][0]["applied"] is False

    from querido.core.metadata import metadata_path

    assert not metadata_path(other, "users").exists()


def test_import_keep_higher_confidence_preserves_human(
    sqlite_path: str, tmp_path: Path, monkeypatch, make_sqlite_db
):
    """Local human description (confidence 1.0) beats an incoming auto-written one (0.8)."""
    monkeypatch.chdir(tmp_path)

    # Source has an auto-written description (confidence 0.8, provenance shape).
    _seed_metadata(
        sqlite_path,
        "users",
        col_description={
            "value": "bundle-auto-written",
            "source": "values",
            "confidence": 0.8,
            "written_at": "2026-01-01T00:00:00+00:00",
            "author": "alice",
        },
    )
    out = tmp_path / "src.qdobundle"
    export_bundle(sqlite_path, ["users"], out, include_column_sets=False)

    # Target has a human-authored description (plain string = confidence 1.0).

    other = make_sqlite_db(str(tmp_path / "other.db"))
    _seed_metadata(other, "users", col_description="local human desc")

    report = import_bundle(out, other, strategy="keep-higher-confidence", apply=True)

    from querido.core.metadata import show_metadata

    meta = show_metadata(other, "users")
    assert meta is not None
    name_col = next(c for c in meta["columns"] if c["name"] == "name")
    assert name_col["description"] == "local human desc"

    actions = report["tables"][0]["field_actions"]
    desc_actions = [a for a in actions if a["column"] == "name" and a["field"] == "description"]
    assert desc_actions and desc_actions[0]["action"] == "skip"


def test_written_at_falls_back_to_mtime_for_legacy_session_name():
    """Regression (L4): a non-ISO ``written_at`` (legacy session name) must not be
    compared lexicographically against a real timestamp; it falls back to mtime."""
    from querido.core.bundle import _written_at_of

    mtime = 1_700_000_000.0
    legacy = {
        "value": True,
        "source": "values",
        "confidence": 0.8,
        "written_at": "my-investigation",  # legacy: session name, not ISO
        "author": "alice",
    }
    iso = {
        "value": True,
        "source": "values",
        "confidence": 0.8,
        "written_at": "2026-01-01T00:00:00+00:00",
        "author": "alice",
    }
    # Legacy session name -> mtime fallback (a real ISO timestamp).
    fallback = _written_at_of(legacy, mtime)
    assert fallback != "my-investigation"
    from datetime import datetime

    datetime.fromisoformat(fallback)
    # A valid ISO written_at is returned verbatim.
    assert _written_at_of(iso, mtime) == "2026-01-01T00:00:00+00:00"


def test_import_all_skips_reports_not_applied(
    sqlite_path: str, tmp_path: Path, monkeypatch, make_sqlite_db
):
    """Regression: a table whose every field action is a skip must report applied=False.

    Re-importing an already-applied bundle (strategy=mine) produces only skips;
    nothing is written, so ``applied`` must be False even in apply mode.
    """
    monkeypatch.chdir(tmp_path)
    # Seed a non-empty value for every importable field on both sides so the
    # merge has nothing to gap-fill: strategy=mine then skips every field and
    # writes nothing, which is the only case where apply must report False.
    _seed_metadata(sqlite_path, "users", col_description="from-bundle", notes="shared note")
    out = tmp_path / "src.qdobundle"
    export_bundle(sqlite_path, ["users"], out, include_column_sets=False)

    other = make_sqlite_db(str(tmp_path / "other.db"))
    _seed_metadata(other, "users", col_description="local-desc", notes="shared note")

    # strategy=mine: local always wins, so every field action is a skip.
    report = import_bundle(out, other, strategy="mine", apply=True)

    actions = report["tables"][0]["field_actions"]
    assert actions, "expected field actions to be present"
    assert all(a["action"] == "skip" for a in actions)
    assert report["tables"][0]["applied"] is False


def test_import_theirs_overrides(sqlite_path: str, tmp_path: Path, monkeypatch, make_sqlite_db):
    monkeypatch.chdir(tmp_path)
    _seed_metadata(sqlite_path, "users", col_description="from-bundle")
    out = tmp_path / "src.qdobundle"
    export_bundle(sqlite_path, ["users"], out, include_column_sets=False)

    other = make_sqlite_db(str(tmp_path / "other.db"))
    _seed_metadata(other, "users", col_description="local-desc")

    import_bundle(out, other, strategy="theirs", apply=True)
    from querido.core.metadata import show_metadata

    meta = show_metadata(other, "users")
    assert meta is not None
    name_col = next(c for c in meta["columns"] if c["name"] == "name")
    assert name_col["description"] == "from-bundle"


def test_import_map_renames_table(sqlite_path: str, tmp_path: Path, monkeypatch, make_sqlite_db):
    monkeypatch.chdir(tmp_path)
    _seed_metadata(sqlite_path, "users", table_description="orig")
    out = tmp_path / "src.qdobundle"
    export_bundle(sqlite_path, ["users"], out, include_column_sets=False)

    # Target has a table named "accounts" with an identical schema.

    other = make_sqlite_db(
        str(tmp_path / "other.db"),
        tables={
            "CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT NOT NULL, age INTEGER)": [
                "INSERT INTO accounts VALUES (1, 'A', 10)",
            ],
        },
    )

    report = import_bundle(out, other, maps={"users": "accounts"}, apply=True)
    assert report["tables"][0]["target_table"] == "accounts"
    assert report["tables"][0]["fingerprint_status"] == "match"

    from querido.core.metadata import metadata_path, show_metadata

    assert metadata_path(other, "accounts").exists()
    meta = show_metadata(other, "accounts")
    assert meta is not None
    assert meta["table"] == "accounts"
    assert meta["table_description"] == "orig"


def test_import_schema_drift_skips_unknown_columns(
    sqlite_path: str, tmp_path: Path, monkeypatch, make_sqlite_db
):
    monkeypatch.chdir(tmp_path)
    _seed_metadata(sqlite_path, "users", col_description="from-bundle")
    out = tmp_path / "src.qdobundle"
    export_bundle(sqlite_path, ["users"], out, include_column_sets=False)

    # Different schema on the target.

    other = make_sqlite_db(
        str(tmp_path / "other.db"),
        tables={
            "CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)": [
                "INSERT INTO users VALUES (1, 'a@b')",
            ],
        },
    )

    report = import_bundle(out, other, apply=True)
    assert report["tables"][0]["fingerprint_status"] == "drift"
    skipped = [
        a for a in report["tables"][0]["field_actions"] if a.get("reason") == "schema_drift"
    ]
    assert skipped


def test_import_column_sets_round_trip(
    sqlite_path: str, tmp_path: Path, monkeypatch, make_sqlite_db
):
    monkeypatch.chdir(tmp_path)

    other_path = make_sqlite_db(str(tmp_path / "other.db"))

    # Single shared config with two named connections so column-set TOML keys
    # don't collide with file-path dots.
    cfg_dir = tmp_path / "qdo-config"
    cfg_dir.mkdir()
    monkeypatch.setenv("QDO_CONFIG", str(cfg_dir))
    (cfg_dir / "connections.toml").write_text(
        # Literal strings (single-quoted) so Windows backslashes survive
        # round-trip — basic strings interpret ``\U`` as a Unicode escape.
        f"[connections.src]\ntype = \"sqlite\"\npath = '{sqlite_path}'\n"
        f"[connections.dst]\ntype = \"sqlite\"\npath = '{other_path}'\n"
    )

    _seed_metadata("src", "users")

    from querido.config import list_column_sets, save_column_set

    save_column_set("src", "users", "default", ["id", "name"])

    out = tmp_path / "src.qdobundle"
    export_bundle("src", ["users"], out)

    import_bundle(out, "dst", maps={"users": "users"}, apply=True)
    sets = list_column_sets(connection="dst")
    assert any(
        entry.get("connection") == "dst"
        and entry.get("table") == "users"
        and entry.get("set") == "default"
        for entry in sets
    )


# -- diff ---------------------------------------------------------------------


def test_diff_reports_only_in_a_and_drift(sqlite_path: str, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_metadata(sqlite_path, "users")

    a = tmp_path / "a.qdobundle"
    export_bundle(sqlite_path, ["users"], a, include_column_sets=False)

    # Modify the on-disk metadata's fingerprint field directly to simulate drift.
    b = tmp_path / "b.qdobundle"
    export_bundle(sqlite_path, ["users"], b, include_column_sets=False)
    meta_path = b / "metadata" / "users.yaml"
    meta = yaml.safe_load(meta_path.read_text())
    meta["schema_fingerprint"] = "ffffffffffffffff"
    meta_path.write_text(yaml.safe_dump(meta, sort_keys=False))

    report = diff_bundles(a, b)
    assert report["schema_drifts"]
    assert report["schema_drifts"][0]["table"] == "users"


# -- CLI ----------------------------------------------------------------------


def test_cli_export_and_inspect(sqlite_path: str, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_metadata(sqlite_path, "users")

    result = runner.invoke(
        app,
        [
            "bundle",
            "export",
            "-c",
            sqlite_path,
            "-t",
            "users",
            "-o",
            str(tmp_path / "out.qdobundle"),
            "--no-column-sets",
        ],
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["bundle", "inspect", str(tmp_path / "out.qdobundle")])
    assert result.exit_code == 0, result.output
    assert "users" in result.output


def test_cli_zip_suffix_writes_zip_archive(sqlite_path: str, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_metadata(sqlite_path, "users")
    output = tmp_path / "users.zip"

    result = runner.invoke(
        app,
        [
            "bundle",
            "export",
            "-c",
            sqlite_path,
            "-t",
            "users",
            "-o",
            str(output),
            "--no-column-sets",
        ],
    )

    assert result.exit_code == 0, result.output
    assert output.is_file()
    assert zipfile.is_zipfile(output)


def test_cli_import_dry_run_and_apply(
    sqlite_path: str, tmp_path: Path, monkeypatch, make_sqlite_db
):
    monkeypatch.chdir(tmp_path)
    _seed_metadata(sqlite_path, "users", table_description="source-desc")

    out = str(tmp_path / "src.qdobundle")
    export_bundle(sqlite_path, ["users"], out, include_column_sets=False)

    other = make_sqlite_db(str(tmp_path / "other.db"))

    # Dry-run
    result = runner.invoke(app, ["bundle", "import", out, "--into", other])
    assert result.exit_code == 0, result.output
    from querido.core.metadata import metadata_path

    assert not metadata_path(other, "users").exists()

    # Apply
    result = runner.invoke(app, ["bundle", "import", out, "--into", other, "--apply"])
    assert result.exit_code == 0, result.output
    assert metadata_path(other, "users").exists()


def test_cli_import_refuses_future_connections_schema_before_apply(
    sqlite_path: str, tmp_path: Path, monkeypatch, make_sqlite_db
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_metadata(sqlite_path, "users", table_description="source-desc")
    bundle = tmp_path / "src.qdobundle"
    export_bundle(sqlite_path, ["users"], bundle, include_column_sets=False)
    target = make_sqlite_db(str(tmp_path / "target.db"))
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "connections.toml").write_text("schema_version = 99\n")
    monkeypatch.setenv("QDO_CONFIG", str(config_dir))

    result = runner.invoke(app, ["bundle", "import", str(bundle), "--into", target, "--apply"])

    from querido.core.metadata import metadata_path

    assert result.exit_code != 0
    assert not metadata_path(target, "users").exists()


def test_cli_import_validates_column_set_store_before_metadata_apply(
    sqlite_path: str, tmp_path: Path, monkeypatch, make_sqlite_db
) -> None:
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "config"
    monkeypatch.setenv("QDO_CONFIG", str(config_dir))
    _seed_metadata(sqlite_path, "users", table_description="source-desc")
    from querido.config import save_column_set

    save_column_set(sqlite_path, "users", "names", ["name"])
    bundle = tmp_path / "src.qdobundle"
    export_bundle(sqlite_path, ["users"], bundle)
    (config_dir / "column_sets.toml").write_text("schema_version = 99\n")
    target = make_sqlite_db(str(tmp_path / "target.db"))

    result = runner.invoke(app, ["bundle", "import", str(bundle), "--into", target, "--apply"])

    from querido.core.metadata import metadata_path

    assert result.exit_code != 0
    assert not metadata_path(target, "users").exists()


def test_cli_bad_map_value(sqlite_path: str, tmp_path: Path, monkeypatch, make_sqlite_db):
    monkeypatch.chdir(tmp_path)
    _seed_metadata(sqlite_path, "users")
    out = str(tmp_path / "src.qdobundle")
    export_bundle(sqlite_path, ["users"], out, include_column_sets=False)

    other = make_sqlite_db(str(tmp_path / "other.db"))

    result = runner.invoke(app, ["bundle", "import", out, "--into", other, "--map", "bogus"])
    assert result.exit_code != 0
