"""TOON encoder conformance tests.

Runs every case from the vendored spec fixtures (see
``tests/fixtures/toon/NOTICE.md``) that targets a shape our encoder
claims to support, and skips the rest with an explicit reason.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from querido.output.toon import ToonUnsupportedShape, encode

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "toon"

# Fixture files we process. Files not listed here are skipped wholesale
# because every case inside uses options/shapes outside our v1 scope.
IN_SCOPE_FILES = [
    "primitives.json",
    "objects.json",
    "arrays-primitive.json",
    "arrays-tabular.json",
    "arrays-nested.json",
    "arrays-objects.json",
    "whitespace.json",
]

# Files fully skipped and why.
OUT_OF_SCOPE_FILES = {
    "delimiters.json": "custom delimiters (tab/pipe) not in v1 scope",
    "key-folding.json": "key folding (§13.4) not in v1 scope",
}


def _load_cases() -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []
    for fname in IN_SCOPE_FILES:
        data = json.loads((FIXTURE_DIR / fname).read_text())
        cases.extend((f"{fname}::{test['name']}", test) for test in data["tests"])
    return cases


def _option_skip_reason(test: dict[str, Any]) -> str | None:
    opts = test.get("options") or {}
    delim = opts.get("delimiter", ",")
    if delim != ",":
        return f"non-comma delimiter ({delim!r})"
    if "keyFolding" in opts and opts["keyFolding"] != "off":
        return "keyFolding option"
    if "flattenDepth" in opts:
        return "flattenDepth option"
    if test.get("shouldError"):
        return "error-case fixture (decode-side concern)"
    return None


@pytest.mark.parametrize(
    ("name", "test"), _load_cases(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_encode_fixture(name: str, test: dict[str, Any]) -> None:
    skip = _option_skip_reason(test)
    if skip:
        pytest.skip(skip)

    indent = (test.get("options") or {}).get("indent", 2)
    expected: str = test["expected"]

    try:
        got = encode(test["input"], indent=indent)
    except ToonUnsupportedShape as e:
        pytest.skip(f"shape out of v1 scope: {e}")

    assert got == expected, f"\n--- expected ---\n{expected!r}\n--- got ---\n{got!r}"


def test_out_of_scope_files_are_acknowledged() -> None:
    """Fail if a vendored fixture file isn't covered by either list."""
    vendored = {p.name for p in FIXTURE_DIR.glob("*.json") if p.name != "fixtures.schema.json"}
    covered = set(IN_SCOPE_FILES) | set(OUT_OF_SCOPE_FILES)
    missing = vendored - covered
    assert not missing, f"new fixture file(s) need triage: {sorted(missing)}"


def test_unsupported_shape_raises() -> None:
    # Array of arrays — §9.2, out of v1 scope.
    with pytest.raises(ToonUnsupportedShape):
        encode({"pairs": [[1, 2], [3, 4]]})


def test_unsupported_non_uniform_array_raises() -> None:
    # Mixed types — §9.4, out of v1 scope.
    with pytest.raises(ToonUnsupportedShape):
        encode({"items": [1, {"a": 1}, "text"]})
