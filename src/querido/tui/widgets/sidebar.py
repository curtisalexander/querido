from __future__ import annotations

from typing import Any

from textual.widgets import Static


class MetadataSidebar(Static):
    """Sidebar showing column metadata and optional stats."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__("", *args, **kwargs)
        self._last_text: str = ""

    def show_column(
        self,
        *,
        table: str,
        column: dict[str, Any] | None,
        quality: dict[str, Any] | None = None,
        connection_name: str = "",
        metadata_present: bool = False,
        category: str | None = None,
        recommended: bool | None = None,
    ) -> None:
        from rich.markup import escape

        def add_section(title: str) -> None:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(f"[bold]{title}[/bold]")

        lines: list[str] = []
        lines.append(f"[bold]{escape(table)}[/bold]")
        if connection_name:
            lines.append(f"[dim]{escape(connection_name)}[/dim]")
        lines.append(
            "[green]metadata available[/green]" if metadata_present else "[dim]no metadata[/dim]"
        )
        lines.append("")

        if not column:
            lines.append("[dim]Select a column to inspect its details.[/dim]")
            self._last_text = "\n".join(lines)
            self.update(self._last_text)
            return

        name = str(column.get("name", ""))
        ctype = str(column.get("type", ""))
        nullable = "nullable" if column.get("nullable") else "not null"
        pk = " [PK]" if column.get("primary_key") else ""
        lines.append(f"[bold cyan]{escape(name)}[/bold cyan]{pk}")
        badge_parts = [escape(ctype), nullable]
        if category:
            badge_parts.append(escape(category))
        if recommended is not None:
            badge_parts.append("recommended" if recommended else "background")
        lines.append("  •  ".join(badge_parts))

        description = column.get("description") or column.get("comment")
        if description:
            lines.append(f"[dim]{escape(str(description))}[/dim]")

        null_pct = column.get("null_pct")
        null_count = column.get("null_count")
        distinct_count = column.get("distinct_count")
        add_section("Profile")
        if null_pct is not None:
            lines.append(f"null rate: {float(null_pct):.1f}% ({int(null_count or 0):,})")
        if distinct_count is not None:
            lines.append(f"distinct: {int(distinct_count):,}")

        min_val = column.get("min")
        max_val = column.get("max")
        if min_val is not None or max_val is not None:
            lines.append(f"range: {escape(str(min_val))} -> {escape(str(max_val))}")

        sample_values = column.get("sample_values") or []
        if sample_values:
            rendered = ", ".join(escape(str(value)) for value in sample_values[:5])
            lines.append(f"samples: {rendered}")

        valid_values = column.get("valid_values") or []
        has_signals = (
            bool(valid_values)
            or bool(column.get("temporal"))
            or bool(column.get("likely_sparse"))
            or bool(column.get("pii"))
        )
        if has_signals:
            add_section("Signals")
        if valid_values:
            rendered = ", ".join(escape(str(value)) for value in valid_values[:8])
            lines.append(f"allowed: {rendered}")

        if column.get("temporal"):
            lines.append("flag: temporal")
        if column.get("likely_sparse"):
            lines.append("flag: likely sparse")
        if column.get("pii"):
            lines.append("flag: pii")

        if quality:
            add_section("Quality")
            status = str(quality.get("status", "ok"))
            status_style = {"ok": "green", "warn": "yellow", "fail": "red"}.get(status, "cyan")
            lines.append(f"quality: [{status_style}]{escape(status)}[/{status_style}]")
            issues = quality.get("issues") or []
            if issues:
                lines.extend(f"- {escape(str(issue))}" for issue in issues[:4])
            else:
                lines.append("[dim]no active quality flags[/dim]")

        self._last_text = "\n".join(lines)
        self.update(self._last_text)
