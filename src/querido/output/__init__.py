def fmt_value(val: object) -> str:
    """Format a value for display, converting None to empty string."""
    if val is None:
        return ""
    return str(val)
