"""Provenance-wrapped metadata field values — the shared read model.

Stored metadata fields may be plain scalars/lists or provenance-wrapped dicts
(``{value, source, confidence, ...}``). Both core readers and every output
renderer need to reduce these to their plain, presentable form, so this helper
lives in its own leaf module rather than as a private function buried inside the
much larger ``metadata.py``. Keeping it here means ``output/`` depends on a
small, named, public concept instead of reaching into ``metadata`` internals.
"""

from __future__ import annotations


def unwrap_field(value: object) -> object | None:
    """Unwrap a stored metadata value to its plain form for read-back.

    * Provenance-wrapped values (``{value, source, confidence, ...}``) are
      unwrapped to their ``value``.
    * Placeholder strings (``<description>``), empty strings, and empty
      lists return ``None`` so callers can treat them as absent.
    """
    if isinstance(value, dict):
        keys = tuple(value.keys())
        if "value" in keys and "source" in keys:
            value = next((v for k, v in value.items() if k == "value"), None)
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.startswith("<"):
            return None
        return stripped
    if isinstance(value, list) and not value:
        return None
    return value
