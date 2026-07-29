# Architecture and data layers

PaperFlow separates the installed application, per-user Workspace, Obsidian
Vault projections, Public Feed, and local User Data.

## Data layers

- **Raw**: immutable source/version snapshots containing factual metadata and
  source URLs, never AI scores or user state.
- **AI**: immutable append-only analyses keyed by paper content hash, provider,
  model, prompt version, schema version, and analysis profile.
- **User**: local sidecars plus `user_*` Obsidian properties. Existing note
  values and user tags are merged and never overwritten by Feed sync.
- **Derived**: Markdown notes, Bases, dashboards, briefs, indexes, and caches;
  these can be rebuilt only after merging User Data.
- **Community Contribution**: immutable, explicitly selected public snapshots.
- **Subscription Cache**: validated read-only remote revisions and retractions;
  it never writes User Annotation, Review, `user_*`, or AI.

User data separates paper state, Annotation, and Review. Annotation Markdown is
the editable truth; JSON is rebuildable. Anchors bind to an immutable PDF
version/hash and retain revision history during reanchoring.

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

Because Derived is applied after the aggregate compatibility record, path
migrations must update modeled rebuildable fields such as `paper_pdf_path`,
`pdf_path`, and `source_pdf_path` in the Derived record before rendering.
Workspace v3 performs those updates atomically. Visual asset `path` values
remain PNG paths and are never rewritten as PDF paths; visual manifest v1 binds
to the source PDF by SHA-256 rather than by a mutable path.

Schema and application versions are independent. Data newer than the installed
reader is rejected; older data requires an explicit migration.

PDFs are version-addressed at
`80 Attachments/Papers/<year>/<paper_id>/v<version>.pdf`; the Derived pdf-index
records every hash and the preferred current version.

## Zotero/Core boundary

Zotero is the primary bibliographic, PDF, and Reader-annotation owner.
PaperFlow's Zotero plugin uses only public object APIs to create or inspect
Collections, items, attachments, and annotations. It never opens or modifies
`zotero.sqlite`. PDF bytes cross only the authenticated loopback staging
protocol; Core verifies offset, PDF magic, size, and SHA-256 before canonical
storage or analysis.

Core owns immutable AI records, mappings, jobs, and SYSTEM_MANAGED annotation
mirror JSON. Obsidian receives the canonical AI projection; Zotero receives a
secondary Markdown attachment through `Zotero.Attachments.importFromFile()`.
Zotero Reader annotations remain the editable truth, while their Core JSON is
read-only and rebuildable. Legacy Obsidian Annotation Notes are preserved but
are not generated for new Zotero annotations.

The loopback API uses short-lived bearer sessions. One valid session can
create a device pairing: Zotero stores the device secret locally and Core
stores only its hash. Later Core restarts issue a fresh session through that
pairing, so long-lived bearer tokens are neither embedded in the plugin nor
committed to a Workspace.

## Localized presentation layer

Generated-paper YAML keys are a stable interoperability contract and remain in
English. PaperFlow Automation adds a locale-sensitive presentation layer over
Obsidian's native Properties panel: Chinese locales see Chinese labels, while
English locales and focused property-name inputs expose the canonical keys.
This layer changes no note content, schema, query, Base, or Feed data.
