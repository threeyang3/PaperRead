# User data migrations

User records currently use schema version 1. Migrations must never overwrite
`user_*` values or note text inside PaperFlow user-note markers.
