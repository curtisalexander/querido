from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    """Status bar showing connection info, row count, filter status, sort."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__("", *args, **kwargs)
        self._last_text: str = ""
        self._table: str = ""
        self._displayed: int = 0
        self._total: int = 0
        self._filtered: bool = False
        self._sort_col: str | None = None
        self._sort_dir: str | None = None

    def update_status(
        self,
        *,
        table: str | None = None,
        displayed: int | None = None,
        total: int | None = None,
        filtered: bool | None = None,
        sort_col: str | None = ...,
        sort_dir: str | None = ...,
    ) -> None:
        if table is not None:
            self._table = table
        if displayed is not None:
            self._displayed = displayed
        if total is not None:
            self._total = total
        if filtered is not None:
            self._filtered = filtered
        if sort_col is not ...:
            self._sort_col = sort_col
        if sort_dir is not ...:
            self._sort_dir = sort_dir

        parts = [f" {self._table}"]
        parts.append(f"  {self._displayed:,}/{self._total:,} rows")
        if self._filtered:
            parts.append("  [filtered]")
        if self._sort_col:
            arrow = "↓" if self._sort_dir == "desc" else "↑"
            parts.append(f"  sorted: {self._sort_col} {arrow}")
        self._last_text = "".join(parts)
        self.update(self._last_text)
