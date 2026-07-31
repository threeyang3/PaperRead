# PDF++ integration

PaperFlow recommends the official `pdf-plus` community plugin for
backlink-based Markdown annotations. PDF editing is disabled in the recommended
settings because a downloaded Raw PDF is immutable. If a user deliberately
enables direct editing, the edited PDF is user-derived and is never published
to a Feed.

PaperFlow parses public Obsidian link syntax and does not call PDF++ private
JavaScript APIs. Missing or incompatible PDF++ falls back to page-only native
PDF links.
