from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import Input, SelectionList, Static
from textual.widgets.selection_list import Selection

if TYPE_CHECKING:
    from querido.connectors.base import Connector

_CATEGORY_ORDER = (
    "time",
    "measure",
    "low_cardinality",
    "other",
    "high_cardinality",
    "sparse",
    "constant",
)

_CATEGORY_LABELS = {
    "constant": "Constant (1 distinct value)",
    "sparse": "Sparse (>90% null)",
    "high_cardinality": "High Cardinality (likely IDs)",
    "time": "Time",
    "measure": "Measure (numeric)",
    "low_cardinality": "Low Cardinality (<50 distinct)",
    "other": "Other",
}

# Categories that are NOT pre-selected by default.
_SKIP_BY_DEFAULT = {"sparse", "constant"}


class ColumnSelectorScreen(ModalScreen[list[str] | None]):
    """Multi-select modal for choosing columns after Tier 1 classification."""

    CSS = """
    ColumnSelectorScreen {
        align: center middle;
    }

    #selector-container {
        width: 80;
        height: 85%;
        background: $surface;
        border: tall $accent;
        padding: 1 2;
    }

    #selector-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }

    #selector-list {
        height: 1fr;
    }

    #selector-footer {
        text-align: center;
        padding-top: 1;
        color: $text-muted;
    }

    #save-input {
        display: none;
        height: 3;
        padding-top: 1;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("enter", "confirm", "Confirm", priority=True),
        Binding("a", "select_all", "All", priority=False),
        Binding("n", "select_none", "None", priority=False),
        Binding("s", "save_set", "Save", priority=False),
    ]

    def __init__(
        self,
        classification: dict,
        stats: list[dict],
        col_info: list[dict],
        *,
        connector: Connector | None = None,
        connection_name: str = "",
        table: str = "",
    ) -> None:
        super().__init__()
        self._classification = classification
        self._stats = stats
        self._col_info = col_info
        self._connector = connector
        self._connection_name = connection_name
        self._table = table
        self._ordered_names: list[str] = []

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical

        stats_by_name: dict[str, dict] = {}
        for s in self._stats:
            stats_by_name[s.get("column_name", "")] = s

        categories = self._classification.get("categories", {})

        selections: list[Selection[str]] = []

        for cat_key in _CATEGORY_ORDER:
            col_names = categories.get(cat_key, [])
            if not col_names:
                continue

            label = _CATEGORY_LABELS.get(cat_key, cat_key)
            # Add a visual separator/header as a disabled selection
            selections.append(
                Selection(f"--- {label} ({len(col_names)}) ---", f"__header__{cat_key}", False)
            )

            pre_select = cat_key not in _SKIP_BY_DEFAULT
            for name in col_names:
                s = stats_by_name.get(name, {})
                col_type = s.get("column_type", "")
                null_pct = s.get("null_pct", "")
                distinct = s.get("distinct_count", "")
                display = f"  {name} ({col_type})  null: {null_pct}%  distinct: {distinct}"
                selections.append(Selection(display, name, pre_select))
                self._ordered_names.append(name)

        with Vertical(id="selector-container"):
            yield Static(
                f"Select columns to profile — {self._table}",
                id="selector-title",
            )
            yield SelectionList[str](*selections, id="selector-list")
            yield Input(
                placeholder="Column set name (then Enter to save)",
                id="save-input",
            )
            yield Static(
                "[a] All  [n] None  [s] Save set  [Enter] Profile selected  [Esc] Cancel",
                id="selector-footer",
            )

    def _get_selected(self) -> list[str]:
        sl = self.query_one("#selector-list", SelectionList)
        return [val for val in sl.selected if not str(val).startswith("__header__")]

    def action_confirm(self) -> None:
        selected = self._get_selected()
        self.dismiss(selected if selected else None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_select_all(self) -> None:
        sl = self.query_one("#selector-list", SelectionList)
        sl.select_all()

    def action_select_none(self) -> None:
        sl = self.query_one("#selector-list", SelectionList)
        sl.deselect_all()

    def action_save_set(self) -> None:
        save_input = self.query_one("#save-input", Input)
        if save_input.display:
            # Already visible — toggle off
            save_input.display = False
            return
        save_input.display = True
        save_input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        set_name = event.value.strip()
        if not set_name:
            return
        selected = self._get_selected()
        if not selected:
            self.notify("No columns selected to save.", severity="warning")
            return
        if not self._connection_name or not self._table:
            self.notify("Cannot save: missing connection/table info.", severity="error")
            return

        from querido.config import save_column_set

        save_column_set(self._connection_name, self._table, set_name, selected)
        self.notify(
            f"Saved column set '{set_name}' ({len(selected)} columns)",
            severity="information",
        )
        save_input = self.query_one("#save-input", Input)
        save_input.display = False
        save_input.value = ""
