# Data model

Raw schema 1 stores immutable source/version facts. AI schema 1 stores
append-only analyses and complete provenance. User schema 1 stores local
reading state and tags. Derived data can be rebuilt only after merging User
Data.

Every versioned record includes `schema_version`, `paper_uid`, and
`extensions`. Unknown legacy fields are placed in `extensions` and survive
round trips. Public Feed schema 1 transfers only Raw and AI records.
