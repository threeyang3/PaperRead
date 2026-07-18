"""Legacy mixed-record Workspace to PaperFlow Workspace schema 1.

Migration ID: workspace-0001-productization
From: legacy/unversioned (0)
To: workspace schema 1
Data types: workspace, raw, ai, user, derived
Reversible: yes, using the per-run snapshot and generated-file manifest

The executable implementation lives in :mod:`paperflow.migration_engine` so it
is installed with the application. Legacy records are preserved in place.
"""

MIGRATION_ID = "workspace-0001-productization"
FROM_VERSION = 0
TO_VERSION = 1
AFFECTS = ("workspace", "raw", "ai", "user", "derived")
REVERSIBLE = True
