# Releasing

Run the full test suite, migration/path/feed/packaging tests, and
`scripts/build_release.py`. Verify every line of `dist/SHA256SUMS` and the
archive privacy tests.

The release workflow creates a draft GitHub Release for `vMAJOR.MINOR.PATCH`
tags. PaperFlow source code is MIT licensed. A public Feed must still declare
its independent data licence; the current workspace uses CC BY 4.0. PyPI
upload and remote publication require explicit owner authorization.
