from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Input, Label


class FilterBar(Horizontal):
    """Filter bar widget — text input for SQL WHERE expressions."""

    class Submitted(Message):
        """Posted when the user presses Enter in the filter input."""

        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def compose(self) -> ComposeResult:
        yield Label("Filter:")
        yield Input(
            placeholder="SQL WHERE expression (e.g. age > 30)",
            id="filter-input",
        )

    def focus_input(self) -> None:
        inp = self.query_one("#filter-input", Input)
        inp.focus()

    def clear_input(self) -> None:
        inp = self.query_one("#filter-input", Input)
        inp.value = ""

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.post_message(self.Submitted(event.value))
