__all__ = ["console", "formats"]


def _fmt(val: object) -> str:
    """Format a value for display, converting None to empty string."""
    if val is None:
        return ""
    return str(val)
