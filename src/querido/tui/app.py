from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.widgets import DataTable

if TYPE_CHECKING:
    from rich.text import Text

    from querido.connectors.base import Connector
    from querido.tui.widgets.filter_bar import FilterBar


class ExploreApp(App):
    """Interactive data exploration TUI for qdo."""

    TITLE = "qdo explore"

    CSS = """
    Screen {
        layout: vertical;
    }

    #filter-bar {
        dock: top;
        height: 3;
        padding: 0 1;
        background: $surface;
    }

    #filter-bar Input {
        width: 1fr;
    }

    #filter-bar Label {
        width: auto;
        padding: 1 1 0 0;
        color: $text-muted;
    }

    #main-area {
        height: 1fr;
    }

    #data-table {
        height: 1fr;
    }

    #sidebar {
        width: 40;
        dock: right;
        background: $surface;
        border-left: tall $accent;
        padding: 1;
        overflow-y: auto;
    }

    #sidebar.hidden {
        display: none;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        background: $accent;
        color: $text;
        padding: 0 1;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("question_mark", "help", "Help", key_display="?"),
        Binding("i", "inspect", "Inspect"),
        Binding("p", "profile", "Profile"),
        Binding("d", "distribution", "Dist"),
        Binding("m", "sidebar", "Metadata"),
        Binding("slash", "filter", "Filter", key_display="/"),
        Binding("escape", "escape", "Clear/Close", show=False),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(
        self,
        *,
        connector: Connector,
        table: str,
        max_rows: int = 1000,
        connection_name: str = "",
    ) -> None:
        super().__init__()
        self.connector = connector
        self.table = table
        self.max_rows = max_rows
        self.connection_name = connection_name
        self._columns: list[dict] = []
        self._rows: list[dict] = []
        self._column_context: dict[str, dict[str, Any]] = {}
        self._column_quality: dict[str, dict[str, Any]] = {}
        self._column_category: dict[str, str] = {}
        self._filter_sql: str | None = None
        self._sort_column: str | None = None
        self._sort_reverse: bool = False
        self._selected_column: str | None = None
        self._row_count: int = 0
        self._sampled: bool = False
        self._metadata_present: bool = False

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal, Vertical
        from textual.widgets import Footer, Header

        from querido.tui.widgets.filter_bar import FilterBar
        from querido.tui.widgets.sidebar import MetadataSidebar
        from querido.tui.widgets.status_bar import StatusBar

        yield Header()
        yield FilterBar(id="filter-bar")
        with Horizontal(id="main-area"):
            with Vertical():
                yield DataTable(id="data-table", cursor_type="cell")
            yield MetadataSidebar(id="sidebar", classes="hidden")
        yield StatusBar(id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        self.title = f"qdo explore — {self.table}"
        await self._load_data(reload_context=True)

    def _metadata_connection(self) -> str:
        return self.connection_name

    def _quick_threshold(self) -> int:
        return int(os.environ.get("QDO_QUICK_THRESHOLD", "50"))

    def _wide_mode_enabled(self) -> bool:
        return len([col for col in self._columns if col.get("name")]) >= self._quick_threshold()

    @staticmethod
    def _category_label(category: str | None) -> str | None:
        labels = {
            "time": "time",
            "measure": "measure",
            "low_cardinality": "low-card",
            "other": "other",
            "high_cardinality": "high-card",
            "sparse": "sparse",
            "constant": "constant",
        }
        if category is None:
            return None
        return labels.get(category, category.replace("_", "-"))

    def _column_is_recommended(self, column_name: str) -> bool:
        category = self._column_category.get(column_name)
        return category not in {"sparse", "constant"}

    def _compute_column_categories(self) -> dict[str, str]:
        from querido.core._utils import build_col_info, classify_columns

        col_info = build_col_info(self._columns)
        stats = [
            {
                "column_name": str(column.get("name", "")),
                "column_type": str(column.get("type", "")),
                "null_pct": column.get("null_pct") or 0,
                "distinct_count": column.get("distinct_count") or 0,
            }
            for column in self._columns
            if column.get("name")
        ]
        classification = classify_columns(stats, col_info, self._row_count)
        return {
            str(name): str(category)
            for name, category in classification.get("column_category", {}).items()
        }

    def _refresh_status(self) -> None:
        from querido.tui.widgets.status_bar import StatusBar

        status = self.query_one("#status-bar", StatusBar)
        selected = self._selected_column or ""
        focus_category = self._category_label(self._column_category.get(selected))
        status.update_status(
            connection=self.connection_name,
            table=self.table,
            displayed=len(self._rows),
            total=self._row_count,
            filtered=self._filter_sql is not None,
            sampled=self._sampled,
            metadata_present=self._metadata_present,
            sort_col=self._sort_column,
            sort_dir="desc" if self._sort_reverse else "asc" if self._sort_column else None,
            focus_col=self._selected_column,
            focus_category=focus_category,
            wide_mode=self._wide_mode_enabled(),
        )

    async def _load_table_context(self) -> None:
        from querido.core.context import get_context

        context = get_context(
            self.connector,
            self.table,
            connection=self._metadata_connection(),
        )
        self._columns = context["columns"]
        self._column_context = {
            str(column.get("name", "")): column
            for column in context["columns"]
            if column.get("name")
        }
        self._row_count = context["row_count"]
        self._column_category = self._compute_column_categories()
        self._sampled = context["sampled"]
        self._metadata_present = bool(context.get("metadata"))
        self._column_quality.clear()

        if not self._selected_column and self._columns:
            self._selected_column = str(self._columns[0].get("name", ""))
        elif self._selected_column and self._selected_column not in self._column_context:
            self._selected_column = (
                str(self._columns[0].get("name", "")) if self._columns else None
            )

    async def _load_data(self, *, reload_context: bool = False) -> None:
        from querido.core.preview import get_preview

        if reload_context or not self._columns:
            await self._load_table_context()

        if self._filter_sql:
            # The filter expression is user-provided SQL typed into the TUI.
            # This is intentional — the user already has direct database access
            # and the TUI is a local-only tool, so this is not a security risk.
            sql = f"select * from {self.table} where {self._filter_sql} limit {self.max_rows}"
            try:
                self._rows = self.connector.execute(sql)
            except Exception as exc:
                self.notify(f"Filter error: {exc}", severity="error")
                self._filter_sql = None
                self._rows = get_preview(self.connector, self.table, limit=self.max_rows)
        else:
            self._rows = get_preview(self.connector, self.table, limit=self.max_rows)

        if self._sort_column:
            self._apply_sort()

        self._populate_table()
        self._refresh_status()
        self._refresh_sidebar()

    def _column_is_warning(self, column_name: str) -> bool:
        column = self._column_context.get(column_name, {})
        null_pct = column.get("null_pct")
        likely_sparse = bool(column.get("likely_sparse"))
        if likely_sparse:
            return True
        return isinstance(null_pct, (int, float)) and float(null_pct) >= 20.0

    def _render_column_label(self, column_name: str) -> Text:
        from rich.text import Text

        column = self._column_context.get(column_name, {})
        text = Text(column_name)
        if column.get("primary_key"):
            text.append(" [PK]", style="bold cyan")
            text.stylize("bold cyan", 0, len(column_name))
        if self._column_is_warning(column_name):
            text.append(" [!]", style="bold yellow")
            text.stylize("yellow", 0, len(column_name))
        if self._sort_column == column_name:
            arrow = " ↓" if self._sort_reverse else " ↑"
            text.append(arrow, style="bold magenta")
            text.stylize("bold underline", 0, len(text))
        return text

    def _render_cell_value(self, column_name: str, value: object) -> Text:
        from rich.text import Text

        if value is None:
            return Text("NULL", style="italic dim red")

        text = Text(str(value))
        column = self._column_context.get(column_name, {})
        if column.get("primary_key"):
            text.stylize("bold cyan")
        elif self._column_is_warning(column_name):
            text.stylize("yellow")
        if self._sort_column == column_name:
            text.stylize("bold")
        return text

    def _display_column_names(self) -> list[str]:
        names = [str(col.get("name", "")) for col in self._columns if col.get("name")]
        if len(names) < self._quick_threshold():
            return names
        if not self._column_category:
            self._column_category = self._compute_column_categories()
        category_rank = {
            "time": 0,
            "measure": 1,
            "low_cardinality": 2,
            "other": 3,
            "high_cardinality": 4,
            "sparse": 5,
            "constant": 6,
        }
        indexed_names = list(enumerate(names))
        indexed_names.sort(
            key=lambda item: (
                category_rank.get(self._column_category.get(item[1], "other"), 99),
                item[0],
            )
        )
        return [name for _, name in indexed_names]

    def _populate_table(self) -> None:
        dt = self.query_one("#data-table", DataTable)
        dt.clear(columns=True)

        column_names = self._display_column_names()
        for column_name in column_names:
            dt.add_column(self._render_column_label(column_name), key=column_name)

        for row in self._rows:
            dt.add_row(*(self._render_cell_value(name, row.get(name)) for name in column_names))

    def _set_selected_column(self, column_name: str | None) -> None:
        if not column_name or column_name not in self._column_context:
            return
        self._selected_column = column_name
        self._refresh_status()
        self._refresh_sidebar()

    def _get_selected_column_quality(self) -> dict[str, Any] | None:
        if not self._selected_column:
            return None
        cached = self._column_quality.get(self._selected_column)
        if cached is not None:
            return cached

        from querido.core.quality import get_quality

        quality = get_quality(
            self.connector,
            self.table,
            columns=[self._selected_column],
            connection=self._metadata_connection(),
        )
        selected = next(iter(quality["columns"]), None)
        if selected is not None:
            self._column_quality[self._selected_column] = selected
        return selected

    def _refresh_sidebar(self) -> None:
        from querido.tui.widgets.sidebar import MetadataSidebar

        sidebar = self.query_one("#sidebar", MetadataSidebar)
        column = self._column_context.get(self._selected_column or "")
        quality = None
        if column and not sidebar.has_class("hidden"):
            quality = self._get_selected_column_quality()
        sidebar.show_column(
            table=self.table,
            column=column,
            quality=quality,
            connection_name=self.connection_name,
            metadata_present=self._metadata_present,
            category=self._category_label(self._column_category.get(self._selected_column or "")),
            recommended=(
                self._column_is_recommended(self._selected_column)
                if self._selected_column in self._column_context
                else None
            ),
        )

    def _apply_sort(self) -> None:
        if not self._sort_column or not self._rows:
            return
        col = self._sort_column
        try:
            self._rows.sort(
                key=lambda r: (r.get(col) is None, r.get(col)),
                reverse=self._sort_reverse,
            )
        except TypeError:
            # Mixed types — fall back to string comparison
            self._rows.sort(
                key=lambda r: (
                    r.get(col) is None,
                    str(r.get(col)) if r.get(col) is not None else "",
                ),
                reverse=self._sort_reverse,
            )

    async def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        col_key = str(event.column_key)
        self._set_selected_column(col_key)
        if self._sort_column == col_key:
            if self._sort_reverse:
                self._sort_column = None
                self._sort_reverse = False
            else:
                self._sort_reverse = True
        else:
            self._sort_column = col_key
            self._sort_reverse = False

        if self._sort_column:
            self._apply_sort()
        else:
            # Sort cleared — reload to restore original order
            await self._load_data()
            return

        self._populate_table()

        self._refresh_status()

    async def on_data_table_column_highlighted(self, event: DataTable.ColumnHighlighted) -> None:
        self._set_selected_column(str(event.column_key))

    def action_filter(self) -> None:
        from querido.tui.widgets.filter_bar import FilterBar

        bar = self.query_one("#filter-bar", FilterBar)
        bar.focus_input()

    def action_escape(self) -> None:
        sidebar = self.query_one("#sidebar")
        if not sidebar.has_class("hidden"):
            sidebar.add_class("hidden")
            return

        if self._filter_sql:
            self._filter_sql = None
            from querido.tui.widgets.filter_bar import FilterBar

            bar = self.query_one("#filter-bar", FilterBar)
            bar.clear_input()
            self.run_worker(self._load_data())

    def action_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar")
        if sidebar.has_class("hidden"):
            sidebar.remove_class("hidden")
            self._refresh_sidebar()
        else:
            sidebar.add_class("hidden")

    def action_inspect(self) -> None:
        from querido.tui.screens.inspect import InspectScreen

        self.push_screen(InspectScreen(self.connector, self.table))

    def action_profile(self) -> None:
        from querido.tui.screens.profile import ProfileScreen

        self.push_screen(
            ProfileScreen(
                self.connector,
                self.table,
                connection_name=self.connection_name,
            )
        )

    def action_distribution(self) -> None:
        from querido.tui.screens.column_picker import ColumnPickerScreen

        def _on_column_selected(col_name: str | None) -> None:
            if col_name is not None:
                from querido.tui.screens.dist import DistScreen

                self.push_screen(DistScreen(self.connector, self.table, col_name))

        self.push_screen(
            ColumnPickerScreen(self._columns, title="Select column for distribution"),
            callback=_on_column_selected,
        )

    def action_help(self) -> None:
        from querido.tui.screens.help import HelpScreen

        self.push_screen(HelpScreen())

    async def action_refresh(self) -> None:
        await self._load_data(reload_context=True)

    async def on_filter_bar_submitted(self, event: FilterBar.Submitted) -> None:
        expr = event.value.strip()
        if expr:
            self._filter_sql = expr
        else:
            self._filter_sql = None
        await self._load_data()
