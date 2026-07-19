# Architecture and data layers

PaperFlow separates the installed application, per-user Workspace, Obsidian
Vault projections, Public Feed, and local User Data.

## Four data layers

- **Raw**: immutable source/version snapshots containing factual metadata and
  source URLs, never AI scores or user state.
- **AI**: immutable append-only analyses keyed by paper content hash, provider,
  model, prompt version, schema version, and analysis profile.
- **User**: local sidecars plus `user_*` Obsidian properties. Existing note
  values and user tags are merged and never overwritten by Feed sync.
- **Derived**: Markdown notes, Bases, dashboards, briefs, indexes, and caches;
  these can be rebuilt only after merging User Data.

Caption-backed visual assets are also Derived. The extractor ranks
architecture/framework/overview/pipeline figures, renders bounded PDF page
regions to PNG, writes a checksummed per-paper manifest, and adaptively embeds
high-value figures in a category-balanced visual guide. Selection stops when
marginal value is low; 12 is a safety ceiling rather than a target.
Missing reliable captions produce no asset instead of a fabricated diagram.
Original captions and in-figure text are not translated.

Derived relationship indexes keep verified citations separate from semantic
similarity, record source/evidence/confidence, and project only Obsidian
wikilinks into the flat paper frontmatter. `compose_record()` is the sole
render input path and merges Raw, AI, User, and Derived layers.

Schema and application versions are independent. Data newer than the installed
reader is rejected; older data requires an explicit migration.

## Localized presentation layer

Generated-paper YAML keys are a stable interoperability contract and remain in
English. PaperFlow Automation adds a locale-sensitive presentation layer over
Obsidian's native Properties panel: Chinese locales see Chinese labels, while
English locales and focused property-name inputs expose the canonical keys.
This layer changes no note content, schema, query, Base, or Feed data.
