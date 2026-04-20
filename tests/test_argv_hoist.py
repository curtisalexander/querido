"""Tests for querido.cli.argv_hoist — the -f/--format argv preprocessor."""

from __future__ import annotations

import pytest

from querido.cli.argv_hoist import hoist_format_flag, split_format_flag


class TestSplitFormatFlag:
    def test_no_format_flag(self) -> None:
        assert split_format_flag(["catalog", "-c", "mydb"]) == (
            ["catalog", "-c", "mydb"],
            None,
        )

    def test_short_flag_with_value(self) -> None:
        assert split_format_flag(["catalog", "-c", "mydb", "-f", "json"]) == (
            ["catalog", "-c", "mydb"],
            "json",
        )

    def test_long_flag_with_value(self) -> None:
        assert split_format_flag(["catalog", "-c", "mydb", "--format", "csv"]) == (
            ["catalog", "-c", "mydb"],
            "csv",
        )

    def test_equals_form(self) -> None:
        assert split_format_flag(["catalog", "-c", "mydb", "--format=yaml"]) == (
            ["catalog", "-c", "mydb"],
            "yaml",
        )

    def test_flag_at_front(self) -> None:
        assert split_format_flag(["-f", "json", "catalog", "-c", "mydb"]) == (
            ["catalog", "-c", "mydb"],
            "json",
        )

    def test_last_occurrence_wins(self) -> None:
        assert split_format_flag(["-f", "json", "catalog", "--format", "csv"]) == (
            ["catalog"],
            "csv",
        )

    def test_dangling_short_flag_no_value(self) -> None:
        # `-f` as final token with nothing after — treated as absent.
        assert split_format_flag(["catalog", "-c", "mydb", "-f"]) == (
            ["catalog", "-c", "mydb"],
            None,
        )

    def test_empty_equals_value(self) -> None:
        # `--format=` preserves the empty string; Click will reject downstream.
        assert split_format_flag(["catalog", "--format="]) == (["catalog"], "")

    def test_empty_input(self) -> None:
        assert split_format_flag([]) == ([], None)


class TestHoistFormatFlag:
    def test_empty_argv(self) -> None:
        assert hoist_format_flag([]) == []

    def test_no_format_flag(self) -> None:
        argv = ["catalog", "-c", "mydb"]
        assert hoist_format_flag(argv) == argv

    def test_hoist_from_end(self) -> None:
        assert hoist_format_flag(["catalog", "-c", "mydb", "-f", "json"]) == [
            "-f",
            "json",
            "catalog",
            "-c",
            "mydb",
        ]

    def test_already_at_front_is_idempotent(self) -> None:
        argv = ["-f", "json", "catalog", "-c", "mydb"]
        assert hoist_format_flag(argv) == argv

    def test_hoist_long_form(self) -> None:
        assert hoist_format_flag(["inspect", "-t", "orders", "--format", "csv"]) == [
            "-f",
            "csv",
            "inspect",
            "-t",
            "orders",
        ]

    def test_hoist_equals_form(self) -> None:
        assert hoist_format_flag(["inspect", "--format=yaml", "-t", "orders"]) == [
            "-f",
            "yaml",
            "inspect",
            "-t",
            "orders",
        ]

    def test_help_not_rewritten(self) -> None:
        # `qdo inspect --help -f json` — don't hoist when --help is present;
        # help display shouldn't suddenly change shape.
        argv = ["inspect", "--help", "-f", "json"]
        assert hoist_format_flag(argv) == argv

    def test_version_not_rewritten(self) -> None:
        argv = ["--version"]
        assert hoist_format_flag(argv) == argv

    def test_value_that_looks_like_a_flag(self) -> None:
        # `--format --debug` would be a user error (no value) but we still
        # swallow --debug as the value rather than second-guessing. Matches
        # Click's own behavior.
        assert hoist_format_flag(["inspect", "--format", "--debug"]) == [
            "-f",
            "--debug",
            "inspect",
        ]


class TestIntegrationWithCli:
    """End-to-end check that `qdo <subcommand> ... -f json` actually parses
    now, via the typer test runner."""

    @pytest.fixture
    def fixture_db(self, tmp_path):
        import duckdb

        db = tmp_path / "test.duckdb"
        con = duckdb.connect(str(db))
        con.execute("create table t (x int)")
        con.execute("insert into t values (1), (2), (3)")
        con.close()
        return db

    def test_format_flag_after_subcommand_works(self, fixture_db) -> None:
        """The motivating case: `qdo inspect -c db -t t -f json` — previously
        fails with 'No such option: -f'; now works because run() hoists."""
        import subprocess
        import sys

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "querido",
                "inspect",
                "-c",
                str(fixture_db),
                "-t",
                "t",
                "-f",
                "json",
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        # JSON output should parse and include the command.
        import json

        payload = json.loads(proc.stdout)
        assert payload["command"] == "inspect"
