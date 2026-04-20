"""Support ``python -m querido`` as an alias for the ``qdo`` entry point.

Used by the workflow runner as a fallback when ``qdo`` isn't on PATH.
"""

from __future__ import annotations

from querido.cli.main import run

if __name__ == "__main__":
    run()
