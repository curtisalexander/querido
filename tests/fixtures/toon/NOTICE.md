# TOON specification fixtures

The JSON fixtures in this directory are vendored verbatim from the
TOON specification repository:

  https://github.com/toon-format/spec/tree/main/tests/fixtures/encode

Copied 2026-04-14. Used by `tests/test_toon.py` to verify that our
in-tree encoder conforms to the spec on shapes it claims to support.

Out-of-scope cases (custom delimiters, key folding, objects-as-list-items,
non-uniform arrays, arrays of arrays) are skipped at collection time — see
`tests/test_toon.py` for the exact filter.

Licensed under MIT (see `LICENSE.toon-spec`). Re-vendor from the spec
repository when we want to target a newer TOON version; any resulting
test failures surface exactly where our encoder diverges from the new
spec.
