from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.widgets import DataTable

if TYPE_CHECKING:
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
        self._filter_sql: str | None = None
        self._sort_column: str | None = None
        self._sort_reverse: bool = False

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
                yield DataTable(id="data-table", cursor_type="row")
            yield MetadataSidebar(id="sidebar", classes="hidden")
        yield StatusBar(id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        self.title = f"qdo explore — {self.table}"
        await self._load_data()

    async def _load_data(self) -> None:
        from querido.core.inspect import get_inspect
        from querido.core.preview import get_preview

        info = get_inspect(self.connector, self.table)
        self._columns = info["columns"]
        row_count = info["row_count"]

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

        dt = self.query_one("#data-table", DataTable)
        dt.clear(columns=True)

        if self._rows:
            for col_name in self._rows[0]:
                dt.add_column(col_name, key=col_name)
            for row in self._rows:
                dt.add_row(*row.values())

        from querido.tui.widgets.status_bar import StatusBar

        status = self.query_one("#status-bar", StatusBar)
        status.update_status(
            table=self.table,
            displayed=len(self._rows),
            total=row_count,
            filtered=self._filter_sql is not None,
            sort_col=self._sort_column,
            sort_dir="desc" if self._sort_reverse else "asc" if self._sort_column else None,
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

        dt = self.query_one("#data-table", DataTable)
        dt.clear()
        for row in self._rows:
            dt.add_row(*row.values())

        from querido.tui.widgets.status_bar import StatusBar

        status = self.query_one("#status-bar", StatusBar)
        status.update_status(
            sort_col=self._sort_column,
            sort_dir="desc" if self._sort_reverse else "asc" if self._sort_column else None,
        )

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
            from querido.tui.widgets.sidebar import MetadataSidebar

            sb = self.query_one("#sidebar", MetadataSidebar)
            sb.show_metadata(self._columns, self.connector, self.table)
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
        await self._load_data()

    async def on_filter_bar_submitted(self, event: FilterBar.Submitted) -> None:
        expr = event.value.strip()
        if expr:
            self._filter_sql = expr
        else:
            self._filter_sql = None
        await self._load_data()
