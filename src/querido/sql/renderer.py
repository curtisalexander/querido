from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "templates"


def render_template(command: str, dialect: str, **kwargs: object) -> str:
    """Load and render a SQL template.

    Tries dialect-specific template first (e.g. profile/sqlite.sql),
    then falls back to common.sql.
    """
    from jinja2 import Environment, FileSystemLoader, TemplateNotFound

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )

    dialect_path = f"{command}/{dialect}.sql"
    common_path = f"{command}/common.sql"

    for path in [dialect_path, common_path]:
        try:
            template = env.get_template(path)
        except TemplateNotFound:
            continue
        return template.render(**kwargs)

    raise FileNotFoundError(f"No SQL template found for command='{command}', dialect='{dialect}'")
