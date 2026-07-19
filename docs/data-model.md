# Data model

Raw schema 1 stores immutable source/version facts. AI schema 1 stores
append-only analyses and complete provenance. User schema 1 stores local
reading state and tags. Derived data can be rebuilt only after merging User
Data.

Every versioned record includes `schema_version`, `paper_uid`, and
`extensions`. Unknown legacy fields are placed in `extensions` and survive
round trips. Public Feed schema 1 transfers only Raw and AI records.

Visual assets are Derived data nested under `extraction.visual_assets` in the
legacy projection and in the Derived record. Each PDF has an adjacent
`<paper-id>.assets/manifest.json` conforming to
`visual-assets.schema.json`. The manifest records only reproducible figure
provenance: PDF hash, figure number, source page, original caption, relative
path, dimensions, classification, score, and image hash. It does not change
Raw, AI, or User schemas and is never part of a Public Feed.

Paper-note schema 2 adds formally migrated flat projections:
`paper_title_display`, entity links, verified local citations, unresolved
citation IDs, and semantic related-paper links. Relationship indexes remain
Derived and retain relationship type, evidence, confidence, and generator
version. `paper_title` remains the unmodified source title.
