# Releasing

Run the full test suite, migration/path/feed/packaging tests, and
`scripts/build_release.py`. Verify every line of `dist/SHA256SUMS` and the
archive privacy tests.

The release workflow creates a published stable GitHub Release for
`vMAJOR.MINOR.PATCH` tags. PaperFlow source code is MIT licensed. A public
Feed must still declare its independent data licence; the current workspace
uses CC BY 4.0. PyPI upload and remote publication require explicit owner
authorization.

PaperRead and ArXiv-data are released independently. A PaperRead tag publishes
software artifacts. An ArXiv-data push validates the Feed and builds the
`ArXiv-data-feed.zip` workflow artifact, but does not create or imply a
PaperRead software version.
