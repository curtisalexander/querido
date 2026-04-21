from __future__ import annotations

from textual.widgets import Static

_UNSET: object = object()


class StatusBar(Static):
    """Status bar showing connection info, row count, filter status, sort."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__("", *args, **kwargs)
        self._last_text: str = ""
        self._connection: str = ""
        self._table: str = ""
        self._displayed: int = 0
        self._total: int = 0
        self._filtered: bool = False
        self._sampled: bool | None = None
        self._metadata_present: bool | None = None
        self._sort_col: str | None = None
        self._sort_dir: str | None = None
        self._focus_col: str | None = None
        self._focus_category: str | None = None
        self._wide_mode: bool | None = None

    def update_status(
        self,
        *,
        connection: str | None = None,
        table: str | None = None,
        displayed: int | None = None,
        total: int | None = None,
        filtered: bool | None = None,
        sampled: bool | None = None,
        metadata_present: bool | None = None,
        sort_col: str | None | object = _UNSET,
        sort_dir: str | None | object = _UNSET,
        focus_col: str | None | object = _UNSET,
        focus_category: str | None | object = _UNSET,
        wide_mode: bool | None = None,
    ) -> None:
        if connection is not None:
            self._connection = connection
        if table is not None:
            self._table = table
        if displayed is not None:
            self._displayed = displayed
        if total is not None:
            self._total = total
        if filtered is not None:
            self._filtered = filtered
        if sampled is not None:
            self._sampled = sampled
        if metadata_present is not None:
            self._metadata_present = metadata_present
        if sort_col is not _UNSET:
            self._sort_col = sort_col  # type: ignore[assignment]
        if sort_dir is not _UNSET:
            self._sort_dir = sort_dir  # type: ignore[assignment]
        if focus_col is not _UNSET:
            self._focus_col = focus_col  # type: ignore[assignment]
        if focus_category is not _UNSET:
            self._focus_category = focus_category  # type: ignore[assignment]
        if wide_mode is not None:
            self._wide_mode = wide_mode

        parts: list[str] = []
        if self._connection:
            parts.append(f"conn {self._connection}")
        if self._table:
            parts.append(f"table {self._table}")
        parts.append(f"rows {self._displayed:,}/{self._total:,}")
        if self._wide_mode:
            parts.append("mode triage")
        if self._filtered:
            parts.append("filter on")
        if self._sampled is not None:
            parts.append("sample sampled" if self._sampled else "sample exact")
        if self._metadata_present is not None:
            parts.append("meta yes" if self._metadata_present else "meta no")
        if self._focus_col:
            focus = f"focus {self._focus_col}"
            if self._focus_category:
                focus += f" · {self._focus_category}"
            parts.append(focus)
        if self._sort_col:
            arrow = "↓" if self._sort_dir == "desc" else "↑"
            parts.append(f"sort {self._sort_col}{arrow}")
        self._last_text = "  •  ".join(parts)
        self.update(self._last_text)
