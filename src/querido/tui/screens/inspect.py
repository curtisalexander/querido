from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static

if TYPE_CHECKING:
    from querido.connectors.base import Connector


class InspectScreen(ModalScreen):
    """Modal overlay showing full column metadata (like qdo inspect -v)."""

    CSS = """
    InspectScreen {
        align: center middle;
    }

    #inspect-container {
        width: 90%;
        height: 80%;
        background: $surface;
        border: tall $accent;
        padding: 1;
    }

    #inspect-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }

    #inspect-table {
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

        with Vertical(id="inspect-container"):
            yield Static(f"Column Metadata — {self.table}", id="inspect-title")
            yield DataTable(id="inspect-table", cursor_type="row")

    def on_mount(self) -> None:
        from querido.core.inspect import get_inspect

        info = get_inspect(self.connector, self.table, verbose=True)
        columns = info["columns"]
        row_count = info["row_count"]
        table_comment = info["table_comment"]

        dt = self.query_one("#inspect-table", DataTable)
        headers = ["Column", "Type", "Nullable", "Default", "PK"]
        if any(c.get("comment") for c in columns):
            headers.append("Comment")

        for h in headers:
            dt.add_column(h, key=h)

        for col in columns:
            row = [
                col.get("name", ""),
                col.get("type", ""),
                "yes" if col.get("nullable") else "no",
                str(col.get("default", "") or ""),
                "yes" if col.get("primary_key") else "",
            ]
            if "Comment" in headers:
                row.append(col.get("comment", "") or "")
            dt.add_row(*row)

        title = self.query_one("#inspect-title", Static)
        comment_str = f"\n{table_comment}" if table_comment else ""
        title.update(f"Column Metadata — {self.table}  ({row_count:,} rows){comment_str}")

    async def action_dismiss(self, result: object = None) -> None:
        self.app.pop_screen()
