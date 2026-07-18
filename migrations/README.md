# PaperFlow migrations

Migrations are registered by data type. Runtime execution is provided by
`paperflow.migration_engine`; this directory documents the release migration
contract and is included in source distributions.

Every migration declares a unique ID, source and target versions, affected
layers, reversibility, and the plan/apply/verify/rollback contract.
