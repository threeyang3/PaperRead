# PaperFlow contributor rules

- This is the application repository; never assume it is a user's Obsidian Vault.
  Use an explicit Vault path and temporary workspaces for tests.
- Preserve `user_*` fields, user-added tags, and `USER_NOTES_START/END` content.
  Raw/AI records are immutable; generated projections must not replace User data.
- Keep flat paper YAML stable. Schema changes need templates, migrations, tests,
  and documentation. Prompt changes require a prompt-version bump.
- Manual paper entry uses official Form Flow. AI sees staged files only and
  cannot edit a Vault. Do not execute scripts obtained from papers or repositories.
- Back up `.obsidian` before altering installed resources. Use PaperFlow migration
  commands for generated data; validate Bases and links after layout changes.
- User-visible dates and scheduler dates use `Asia/Shanghai`.
- Paper figures need original captions and rebuildable provenance. Derived local
  images and personal notes must never enter public Feeds.
- Run the complete Python suite and all JavaScript integration suites for code
  changes. Keep CI gates in sync with newly added integration suites.
- Reconcile current guides with behavior. Put machine-specific acceptance evidence
  in dated audits and distinguish previews from published releases.
