from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import Static


class HelpScreen(ModalScreen):
    """Help overlay showing key bindings."""

    CSS = """
    HelpScreen {
        align: center middle;
    }

    #help-container {
        width: 50;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: tall $accent;
        padding: 1 2;
    }

    #help-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("q", "dismiss", "Close"),
        Binding("question_mark", "dismiss", "Close"),
    ]

    HELP_TEXT = """\
[bold]Key Bindings[/bold]

  [bold cyan]q[/]          Quit
  [bold cyan]?[/]          Show this help
  [bold cyan]i[/]          Inspect column metadata
  [bold cyan]m[/]          Toggle metadata sidebar
  [bold cyan]/[/]          Focus filter bar
  [bold cyan]Escape[/]     Clear filter / close overlay
  [bold cyan]r[/]          Refresh data

[bold]Data Table[/bold]

  Click a column header to sort (asc → desc → none).
  Use arrow keys to navigate rows.

[bold]Filter Bar[/bold]

  Type a SQL WHERE expression and press Enter.
  Examples: [dim]age > 30[/], [dim]name LIKE '%smith%'[/]
  Press Escape to clear the filter.
"""

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical

        with Vertical(id="help-container"):
            yield Static("qdo explore — Help", id="help-title")
            yield Static(self.HELP_TEXT)

    def action_dismiss(self) -> None:
        self.app.pop_screen()
