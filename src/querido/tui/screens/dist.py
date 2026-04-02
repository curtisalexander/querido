from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static

if TYPE_CHECKING:
    from querido.connectors.base import Connector


class DistScreen(ModalScreen):
    """Modal overlay showing distribution for a single column."""

    CSS = """
    DistScreen {
        align: center middle;
    }

    #dist-container {
        width: 80%;
        height: 80%;
        background: $surface;
        border: tall $accent;
        padding: 1;
    }

    #dist-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }

    #dist-table {
        height: 1fr;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("q", "dismiss", "Close"),
    ]

    def __init__(self, connector: Connector, table: str, column: str) -> None:
        super().__init__()
        self.connector = connector
        self.table = table
        self.column = column

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical

        with Vertical(id="dist-container"):
            yield Static(f"Distribution — {self.table}.{self.column}", id="dist-title")
            yield DataTable(id="dist-table", cursor_type="row")

    def on_mount(self) -> None:
        from querido.core.dist import get_distribution

        try:
            result = get_distribution(self.connector, self.table, self.column)
        except Exception as exc:
            title = self.query_one("#dist-title", Static)
            title.update(f"Distribution — {self.table}.{self.column}\n[red]Error: {exc}[/red]")
            return

        mode = result["mode"]
        total = result["total_rows"]
        nulls = result.get("null_count", 0) or 0

        title = self.query_one("#dist-title", Static)
        title.update(
            f"Distribution — {self.table}.{self.column}  ({mode}, {total:,} rows, {nulls:,} nulls)"
        )

        dt = self.query_one("#dist-table", DataTable)

        if mode == "numeric":
            buckets = result.get("buckets", [])
            max_count = max((b["count"] for b in buckets), default=1) or 1
            dt.add_column("Range", key="range")
            dt.add_column("Count", key="count")
            dt.add_column("Bar", key="bar")
            for b in buckets:
                bar_len = int(b["count"] / max_count * 30)
                bar = "\u2588" * bar_len
                dt.add_row(
                    f"{b['bucket_min']} - {b['bucket_max']}",
                    f"{b['count']:,}",
                    bar,
                )
        else:
            values = result.get("values", [])
            max_count = max((v["count"] for v in values), default=1) or 1
            dt.add_column("Value", key="value")
            dt.add_column("Count", key="count")
            dt.add_column("Bar", key="bar")
            for v in values:
                bar_len = int(v["count"] / max_count * 30)
                bar = "\u2588" * bar_len
                display_val = "(NULL)" if v["value"] is None else str(v["value"])
                dt.add_row(display_val, f"{v['count']:,}", bar)

    async def action_dismiss(self, result: object = None) -> None:
        self.app.pop_screen()
