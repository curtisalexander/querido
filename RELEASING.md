# Releasing qdo

The release pipeline is tag-driven: pushing a `v*` tag runs
`.github/workflows/release.yml` → build → install-from-wheel smoke test →
GitHub Release with artifacts → **PyPI publish via trusted publishing**.

Merging to `main` never publishes anything. Nothing reaches PyPI until a
`v*` tag is pushed *and* the one-time setup below is complete.

## One-time PyPI setup (not yet done)

Do these once, before the first `v0.2.0` tag:

1. **Add a pending trusted publisher on PyPI.**
   Log in at <https://pypi.org> → your account → *Publishing* → *Add a new
   pending publisher* with exactly:
   - PyPI project name: `querido`
   - Owner: `curtisalexander`
   - Repository: `querido`
   - Workflow name: `release.yml`
   - Environment name: `pypi`

   ("Pending" because the project doesn't exist on PyPI yet — the first
   successful publish claims the name and converts it to a normal trusted
   publisher.)

2. **Create the GitHub environment.**
   Repo → *Settings* → *Environments* → *New environment* → name it `pypi`.
   No secrets are needed (trusted publishing uses OIDC, not a token).
   Optionally add yourself as a required reviewer — that makes every PyPI
   publish pause for a manual approval click, a nice safety valve.

## Cutting a release (e.g. v0.2.0)

1. Confirm `main` is green and the version is right:
   - `pyproject.toml` `version` and `src/querido/__init__.py` `__version__`
     match the tag you're about to cut (both are `0.2.0` now).
   - `CHANGELOG.md` has a dated section for the version (0.2.0 is done).
2. Tag and push (a **new** tag — `scripts/retag.sh` is only for moving an
   existing release tag to a new commit):

   ```bash
   git checkout main && git pull
   git tag v0.2.0
   git push origin v0.2.0
   ```

3. Watch the Release workflow: build → smoke test → GitHub Release →
   `publish-pypi`. If the trusted publisher isn't configured yet, only the
   `publish-pypi` job fails — the GitHub Release still ships, and you can
   re-run just that job after finishing the one-time setup.

## Post-release: clean-room verification (REVIEW_FINDINGS L35)

From an empty temp directory, with no repo checkout involved:

```bash
uv tool install querido
qdo --version
qdo agent list
python -c "import sqlite3; c = sqlite3.connect('t.db'); c.execute('create table t (id integer primary key, s text)'); c.execute(\"insert into t values (1, 'x')\"); c.commit()"
qdo preview -c t.db -t t -r 1 -f json
qdo context -c t.db -t t
qdo tutorial explore   # interactive; walk at least lesson 1
uv tool uninstall querido
```

Also spot-check the extras: `uv tool install 'querido[duckdb]'` and
`'querido[all]'`. Tick L35 in docs/reviews/REVIEW_FINDINGS.md when this passes
against the live PyPI package.

Note: a pre-publish variant of this check (installing the locally built
0.2.0 wheel into a fresh venv in a temp dir) was run 2026-07-06 and passed;
L35 stays open until it's re-run against PyPI itself.

## After 0.2.0

Per PLAN.md: dogfood week first, then the MCP thin wrapper
([docs/research/mcp-wrapper-design.md](docs/research/mcp-wrapper-design.md))
as the 0.3.0 headline.
