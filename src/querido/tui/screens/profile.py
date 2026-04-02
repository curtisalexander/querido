from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static

if TYPE_CHECKING:
    from querido.connectors.base import Connector


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

    def __init__(self, connector: Connector, table: str) -> None:
        super().__init__()
        self.connector = connector
        self.table = table

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical

        with Vertical(id="profile-container"):
            yield Static(f"Profile — {self.table}", id="profile-title")
            yield DataTable(id="profile-table", cursor_type="row")

    def on_mount(self) -> None:
        from querido.core.profile import get_profile

        try:
            result = get_profile(self.connector, self.table)
        except Exception as exc:
            title = self.query_one("#profile-title", Static)
            title.update(f"Profile — {self.table}\n[red]Error: {exc}[/red]")
            return

        stats = result["stats"]
        row_count = result["row_count"]
        sampled = result["sampled"]
        sample_size = result["sample_size"]

        title = self.query_one("#profile-title", Static)
        sample_note = f"  (sampled {sample_size:,})" if sampled and sample_size else ""
        title.update(f"Profile — {self.table}  ({row_count:,} rows{sample_note})")

        dt = self.query_one("#profile-table", DataTable)
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

    async def action_dismiss(self, result: object = None) -> None:
        self.app.pop_screen()
