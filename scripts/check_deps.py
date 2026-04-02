#!/usr/bin/env python3
"""Check for outdated dependencies with supply-chain-aware quarantine.

Queries PyPI for release dates and flags packages that were published
too recently to trust.  Uses uv for the outdated check and uv audit
for known vulnerabilities.

Usage:
    uv run python scripts/check_deps.py              # default 7-day quarantine
    uv run python scripts/check_deps.py --days 3     # 3-day quarantine
    uv run python scripts/check_deps.py --audit      # also run uv audit
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Terminal formatting
# ---------------------------------------------------------------------------

_IS_TTY = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _IS_TTY else text


def bold(t: str) -> str:
    return _c("1", t)


def dim(t: str) -> str:
    return _c("2", t)


def green(t: str) -> str:
    return _c("32", t)


def yellow(t: str) -> str:
    return _c("33", t)


def red(t: str) -> str:
    return _c("31", t)


def cyan(t: str) -> str:
    return _c("36", t)


# ---------------------------------------------------------------------------
# PyPI metadata
# ---------------------------------------------------------------------------


def fetch_pypi_info(package: str) -> dict | None:
    """Fetch package metadata from the PyPI JSON API."""
    url = f"https://pypi.org/pypi/{package}/json"
    req = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except (URLError, json.JSONDecodeError, TimeoutError):
        return None


def get_release_date(pypi_data: dict, version: str) -> datetime | None:
    """Extract the upload date for a specific version."""
    releases = pypi_data.get("releases", {})
    files = releases.get(version, [])
    if not files:
        return None
    # Use the earliest upload time for this version
    dates = []
    for f in files:
        ts = f.get("upload_time_iso_8601")
        if ts:
            dates.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
    return min(dates) if dates else None


def get_vulnerabilities(pypi_data: dict) -> list[dict]:
    """Return known vulnerabilities from PyPI metadata."""
    return pypi_data.get("vulnerabilities", [])


def is_yanked(pypi_data: dict, version: str) -> bool:
    """Check if a specific version has been yanked."""
    releases = pypi_data.get("releases", {})
    files = releases.get(version, [])
    return any(f.get("yanked", False) for f in files)


# ---------------------------------------------------------------------------
# uv commands
# ---------------------------------------------------------------------------


def get_outdated() -> list[dict]:
    """Run uv pip list --outdated and return parsed JSON."""
    result = subprocess.run(
        ["uv", "pip", "list", "--outdated", "--format", "json"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        print(red(f"Error running uv pip list --outdated:\n{result.stderr}"))
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def run_audit() -> str:
    """Run uv audit and return output."""
    result = subprocess.run(
        ["uv", "audit"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    return result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def print_table(rows: list[dict], quarantine_days: int) -> None:
    """Print a formatted table of outdated dependencies."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=quarantine_days)

    # Column widths
    w_name = max(len("Package"), max((len(r["name"]) for r in rows), default=7))
    w_cur = max(len("Current"), max((len(r["version"]) for r in rows), default=7))
    w_lat = max(len("Latest"), max((len(r["latest_version"]) for r in rows), default=6))
    w_date = 12  # "YYYY-MM-DD" + padding
    w_age = 10
    w_status = 12

    def hdr(text: str, width: int) -> str:
        return bold(text.ljust(width))

    header = (
        f"  {hdr('Package', w_name)}  "
        f"{hdr('Current', w_cur)}  "
        f"{hdr('Latest', w_lat)}  "
        f"{hdr('Published', w_date)}  "
        f"{hdr('Age', w_age)}  "
        f"{hdr('Status', w_status)}"
    )
    sep = "  " + dim("─" * (w_name + w_cur + w_lat + w_date + w_age + w_status + 10))

    print()
    print(header)
    print(sep)

    safe_count = 0
    quarantine_count = 0
    warning_count = 0

    for r in rows:
        name = r["name"].ljust(w_name)
        current = r["version"].ljust(w_cur)
        latest = r["latest_version"].ljust(w_lat)

        release_date = r.get("_release_date")
        vulns = r.get("_vulns", [])
        yanked = r.get("_yanked", False)

        if release_date:
            date_str = release_date.strftime("%Y-%m-%d").ljust(w_date)
            age_delta = now - release_date
            age_days = age_delta.days

            if age_days == 0:
                age_str = "today"
            elif age_days == 1:
                age_str = "1 day"
            elif age_days < 30:
                age_str = f"{age_days} days"
            elif age_days < 365:
                age_str = f"{age_days // 30} months"
            else:
                age_str = f"{age_days // 365}y {(age_days % 365) // 30}m"
            age_str = age_str.ljust(w_age)
        else:
            date_str = dim("unknown").ljust(w_date)
            age_str = dim("?").ljust(w_age)
            age_days = 999  # treat unknown as safe

        # Determine status
        if yanked:
            status = red("YANKED")
            warning_count += 1
        elif vulns:
            vuln_ids = ", ".join(v.get("id", "?") for v in vulns[:2])
            status = red(f"VULN: {vuln_ids}")
            warning_count += 1
        elif release_date and release_date > cutoff:
            status = yellow(f"< {quarantine_days}d")
            quarantine_count += 1
        else:
            status = green("safe")
            safe_count += 1

        print(f"  {name}  {current}  {latest}  {date_str}  {age_str}  {status}")

    print(sep)
    print()

    # Summary
    total = len(rows)
    parts = []
    if safe_count:
        parts.append(green(f"{safe_count} safe to update"))
    if quarantine_count:
        parts.append(yellow(f"{quarantine_count} in quarantine (< {quarantine_days} days)"))
    if warning_count:
        parts.append(red(f"{warning_count} need attention"))
    print(f"  {bold(f'{total} outdated')} — {', '.join(parts)}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check for outdated dependencies with supply-chain quarantine.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Quarantine period in days (default: 7). Recent packages are flagged.",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Also run uv audit to check for known vulnerabilities.",
    )
    args = parser.parse_args()

    print()
    print(f"  {bold('qdo dependency check')}")
    print(f"  Quarantine period: {cyan(f'{args.days} days')}")
    print(f"  {dim('Packages published within this window will be flagged.')}")
    print()

    # Step 1: Get outdated packages
    print(f"  {dim('Checking for outdated packages...')}")
    outdated = get_outdated()

    if not outdated:
        print(f"\n  {green('All dependencies are up to date!')}\n")
    else:
        # Step 2: Enrich with PyPI metadata
        print(f"  {dim(f'Found {len(outdated)} outdated. Fetching PyPI metadata...')}")

        for pkg in outdated:
            pypi_data = fetch_pypi_info(pkg["name"])
            if pypi_data:
                pkg["_release_date"] = get_release_date(pypi_data, pkg["latest_version"])
                pkg["_vulns"] = get_vulnerabilities(pypi_data)
                pkg["_yanked"] = is_yanked(pypi_data, pkg["latest_version"])
            else:
                pkg["_release_date"] = None
                pkg["_vulns"] = []
                pkg["_yanked"] = False

        # Sort: warnings first, then quarantined, then safe (by age ascending)
        def sort_key(r: dict) -> tuple[int, int]:
            if r.get("_yanked") or r.get("_vulns"):
                priority = 0
            elif r.get("_release_date") and r["_release_date"] > datetime.now(UTC) - timedelta(
                days=args.days
            ):
                priority = 1
            else:
                priority = 2
            age = (datetime.now(UTC) - r["_release_date"]).days if r.get("_release_date") else 9999
            return (priority, age)

        outdated.sort(key=sort_key)
        print_table(outdated, args.days)

    # Step 3: Audit
    if args.audit:
        print(f"  {dim('Running uv audit...')}")
        print()
        audit_output = run_audit()
        if "No known vulnerabilities found" in audit_output or not audit_output.strip():
            print(f"  {green('uv audit: No known vulnerabilities found.')}")
        else:
            print(audit_output)
        print()


if __name__ == "__main__":
    main()
