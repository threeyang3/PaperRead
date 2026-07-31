# PaperFlow PDF++ copy format

PaperFlow stores the stable Obsidian/PDF++ backlink itself:

```text
[[{{filePath}}#page={{page}}&selection={{selection}}&color={{colorName}}]]
```

PDF++ settings differ between releases, so PaperFlow does not overwrite an
existing copy-format list. `integration configure pdf-plus` produces a `.new`
candidate when a merge is required. A page-only native Obsidian link remains a
valid fallback.
