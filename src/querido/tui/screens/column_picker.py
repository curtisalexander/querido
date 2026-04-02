from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static


class ColumnPickerScreen(ModalScreen[str | None]):
    """Modal for selecting a column from a list."""

    CSS = """
    ColumnPickerScreen {
        align: center middle;
    }

    #picker-container {
        width: 50;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: tall $accent;
        padding: 1 2;
    }

    #picker-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }

    #picker-list {
        height: auto;
        max-height: 20;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("q", "cancel", "Cancel"),
    ]

    def __init__(self, columns: list[dict], title: str = "Select column") -> None:
        super().__init__()
        self._columns = columns
        self._title = title

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical

        with Vertical(id="picker-container"):
            yield Static(self._title, id="picker-title")
            option_list = OptionList(id="picker-list")
            for col in self._columns:
                name = col.get("name", "")
                ctype = col.get("type", "")
                option_list.add_option(f"{name} ({ctype})")
            yield option_list

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        if 0 <= idx < len(self._columns):
            col_name = self._columns[idx]["name"]
            self.dismiss(col_name)

    def action_cancel(self) -> None:
        self.dismiss(None)
