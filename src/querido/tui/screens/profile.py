from __future__ import annotations

import os
from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static

if TYPE_CHECKING:
    from querido.connectors.base import Connector
    from querido.core.profile import ProfileResult


class ProfileScreen(ModalScreen):
    """Modal overlay showing column profile statistics."""

    CSS = """
    ProfileScreen {
        align: center middle;
    }

    #profile-container {
        width: 95%;
        height: 85%;
        background: $surface;
        border: tall $accent;
        padding: 1;
    }

    #profile-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }

    #profile-table {
        height: 1fr;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("q", "dismiss", "Close"),
    ]

    def __init__(
        self,
        connector: Connector,
        table: str,
        *,
        connection_name: str = "",
    ) -> None:
        super().__init__()
        self.connector = connector
        self.table = table
        self._connection_name = connection_name

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical

        with Vertical(id="profile-container"):
            yield Static(f"Profile — {self.table}", id="profile-title")
            yield DataTable(id="profile-table", cursor_type="row")

    def on_mount(self) -> None:
        self.run_worker(self._run_profile())

    async def _run_profile(self) -> None:
        try:
            col_meta = self.connector.get_columns(self.table)
        except Exception as exc:
            self._show_error(str(exc))
            return

        quick_threshold = int(os.environ.get("QDO_QUICK_THRESHOLD", "50"))
        is_wide = len(col_meta) >= quick_threshold

        if is_wide:
            await self._tiered_profile()
        else:
            await self._full_profile()

    async def _full_profile(self, columns: str | None = None) -> None:
        from querido.core.profile import get_profile

        try:
            result = get_profile(self.connector, self.table, columns=columns)
        except Exception as exc:
            self._show_error(str(exc))
            return

        self._populate_table(result)

    async def _tiered_profile(self) -> None:
        """Wide table: quick profile -> classify -> column selector -> full profile."""
        from querido.core._utils import classify_columns
        from querido.core.profile import get_profile

        # Tier 1: quick stats
        try:
            result = get_profile(self.connector, self.table, quick=True)
        except Exception as exc:
            self._show_error(str(exc))
            return

        classification = classify_columns(result["stats"], result["col_info"], result["row_count"])

        from querido.tui.screens.column_selector import ColumnSelectorScreen

        def _on_columns_selected(selected: list[str] | None) -> None:
            if selected is None:
                # User cancelled — show the quick results as-is
                self._populate_table(result)
                return
            # Tier 2: full profile on selected columns
            self.run_worker(self._full_profile(columns=",".join(selected)))

        self.app.push_screen(
            ColumnSelectorScreen(
                classification,
                result["stats"],
                result["col_info"],
                connector=self.connector,
                connection_name=self._connection_name,
                table=self.table,
            ),
            callback=_on_columns_selected,
        )

    def _populate_table(self, result: ProfileResult) -> None:
        stats = result["stats"]
        row_count = result["row_count"]
        sampled = result["sampled"]
        sample_size = result["sample_size"]
        quick = result.get("quick", False)

        title = self.query_one("#profile-title", Static)
        sample_note = f"  (sampled {sample_size:,})" if sampled and sample_size else ""
        quick_note = "  [dim](quick mode)[/dim]" if quick else ""
        title.update(f"Profile — {self.table}  ({row_count:,} rows{sample_note}){quick_note}")

        dt = self.query_one("#profile-table", DataTable)
        dt.clear(columns=True)

        headers = [
            "Column",
            "Type",
            "Nulls",
            "Null %",
            "Distinct",
            "Min",
            "Max",
            "Mean",
            "Median",
            "Stddev",
        ]
        for h in headers:
            dt.add_column(h, key=h)

        for s in stats:
            dt.add_row(
                s.get("column_name", ""),
                s.get("column_type", ""),
                str(s.get("null_count", "") or ""),
                str(s.get("null_pct", "") or ""),
                str(s.get("distinct_count", "") or ""),
                str(s.get("min_val") if s.get("min_val") is not None else ""),
                str(s.get("max_val") if s.get("max_val") is not None else ""),
                str(s.get("mean_val") if s.get("mean_val") is not None else ""),
                str(s.get("median_val") if s.get("median_val") is not None else ""),
                str(s.get("stddev_val") if s.get("stddev_val") is not None else ""),
            )

    def _show_error(self, msg: str) -> None:
        title = self.query_one("#profile-title", Static)
        title.update(f"Profile — {self.table}\n[red]Error: {msg}[/red]")

    async def action_dismiss(self, result: object = None) -> None:
        self.app.pop_screen()
