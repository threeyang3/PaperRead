# Path templates

Major Raw, AI, User, Derived, PDF, note, Base, dashboard, brief, Inbox, cache,
log, backup, and state roots are configurable.

Templates accept only allowlisted variables such as `source`, `paper_id`,
`year`, `title`, `first_author`, `primary_category`, `type`, `primary_topic`,
`method_family`, `analysis_profile`, and `analysis_id`. Filters are `slug`,
`lower`, `upper`, `truncate`, `replace`, `default`, `first`, and `join`.

Expressions, attribute access, calls, absolute paths, traversal, Windows
reserved names, illegal characters, trailing dots, and overlong results are
blocked or sanitized. Use `paths variables`, `preview`, `validate`, and
`migrate --dry-run` before applying path changes.
