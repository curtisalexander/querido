import tomllib
from datetime import date, timedelta
from pathlib import Path

import pytest

from querido import __version__, _json


def test_json_encoder_handles_supported_database_scalars() -> None:
    payload = {"day": date(2026, 7, 23), "elapsed": timedelta(days=1, seconds=2)}

    assert _json.loads(_json.dumps(payload)) == {
        "day": "2026-07-23",
        "elapsed": "1 day, 0:00:02",
    }


def test_json_encoder_rejects_unknown_objects() -> None:
    with pytest.raises(TypeError, match="not JSON serializable"):
        _json.dumps({"value": object()})


def test_runtime_version_matches_package_metadata() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    assert __version__ == pyproject["project"]["version"]
