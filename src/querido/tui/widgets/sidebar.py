from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Static

if TYPE_CHECKING:
    from querido.connectors.base import Connector


class MetadataSidebar(Static):
    """Sidebar showing column metadata and optional stats."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__("", *args, **kwargs)

    def show_metadata(
        self,
        columns: list[dict],
        connector: Connector,
        table: str,
    ) -> None:
        lines: list[str] = []
        lines.append(f"[bold]{table}[/bold]")
        lines.append(f"{len(columns)} columns\n")

        for col in columns:
            name = col.get("name", "")
            ctype = col.get("type", "")
            nullable = "nullable" if col.get("nullable") else "not null"
            pk = " [PK]" if col.get("primary_key") else ""
            comment = col.get("comment")

            lines.append(f"[bold cyan]{name}[/bold cyan]{pk}")
            lines.append(f"  {ctype}, {nullable}")
            if comment:
                lines.append(f"  [dim]{comment}[/dim]")
            lines.append("")

        self.update("\n".join(lines))
