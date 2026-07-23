# Releasing qdo

The release pipeline is tag-driven: pushing a `v*` tag runs
`.github/workflows/release.yml` → validate tag and versions → build → smoke-test
the wheel and sdist → publish the artifacts to GitHub Releases. PyPI publishing
is a separate, explicitly enabled trusted-publishing job.

Merging to `main` never publishes anything. Nothing reaches PyPI until a
`v*` tag is pushed, the one-time setup below is complete, and the repository
variable `PUBLISH_PYPI` is set to `true`. It is intentionally unset for now.

## One-time PyPI setup (not yet done)

Do these once, immediately before the first PyPI publication:

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

3. **Enable publication only when ready.**
   Repo → *Settings* → *Secrets and variables* → *Actions* → *Variables* → add
   `PUBLISH_PYPI` with value `true`. Until then, tags still create tested GitHub
   Releases but the PyPI job is skipped. Remove or change the variable to stop
   publication again.

## Cutting a release (e.g. v0.2.0)

1. Confirm `main` is green and the version is right:
   - `pyproject.toml` `version` and `src/querido/__init__.py` `__version__`
     match the tag you're about to cut (both are `0.2.0` now).
   - Move the prepared 0.2.0 changes in `CHANGELOG.md` from `[Unreleased]` to a
     dated `0.2.0` section.
2. Tag and push (a **new** tag — `scripts/retag.sh` is only for moving an
   existing, unpublished GitHub release tag to a new commit; it refuses while
   that tag's release workflow is active or after the version reaches PyPI):

   ```bash
   git checkout main && git pull
   git tag v0.2.0
   git push origin v0.2.0
   ```

3. Watch the Release workflow. After the shared validation, build, and smoke
   tests pass, the GitHub Release ships. The `publish-pypi` job is skipped
   unless `PUBLISH_PYPI=true`; once enabled, it publishes independently through
   the protected `pypi` environment.

## Post-release: clean-room verification (REVIEW_FINDINGS L35)

From an empty temp directory, with no repo checkout involved:

```bash
uv tool install querido
qdo --version
qdo agent list
python -c "import sqlite3; c = sqlite3.connect('t.db'); c.execute('create table t (id integer primary key, s text)'); c.execute(\"insert into t values (1, 'x')\"); c.commit()"
qdo preview -c t.db -t t -r 1 -f json
qdo context -c t.db -t t
uv tool uninstall querido

uv tool install 'querido[duckdb]'
qdo tutorial explore   # interactive; walk at least lesson 1
uv tool uninstall querido

uv tool install 'querido[all]'
qdo --help
uv tool uninstall querido
```

Complete the corresponding release-gate item in [PLAN.md](PLAN.md) when these
core, DuckDB, and all-extras checks pass against the live PyPI package. The
original L35 finding is preserved in the
[archived review](docs/archive/reviews/2026-06-10-review-findings.md).

Note: a pre-publish variant of this check (installing the locally built
0.2.0 wheel into a fresh venv in a temp dir) was run 2026-07-06 and passed;
L35 stays open until it's re-run against PyPI itself.

## After 0.2.0

Dogfood first. No 0.3.0 feature is committed; candidates remain in
[IDEAS.md](IDEAS.md) until use creates concrete pull.
