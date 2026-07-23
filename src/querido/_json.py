"""Canonical JSON encoding for qdo's public data values."""

from __future__ import annotations

import json as _json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

JSONDecodeError = _json.JSONDecodeError


def _default(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID, Path)):
        return str(value)
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return str(bytes(value))
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def dumps(value: Any, *args: Any, **kwargs: Any) -> str:
    """Serialize supported database scalars and reject unknown objects."""
    if kwargs.get("default") is str:
        kwargs["default"] = _default
    else:
        kwargs.setdefault("default", _default)
    return _json.dumps(value, *args, **kwargs)


def loads(value: str | bytes | bytearray, *args: Any, **kwargs: Any) -> Any:
    return _json.loads(value, *args, **kwargs)
