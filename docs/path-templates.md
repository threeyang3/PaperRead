# Path templates

Major Raw, AI, User, Derived, PDF, note, Base, dashboard, brief, Inbox, cache,
log, backup, and state roots are configurable.

Templates accept only allowlisted variables such as `source`, `paper_id`,
`year`, `title`, `first_author`, `primary_category`, `type`, `primary_topic`,
`method_family`, `analysis_profile`, and `analysis_id`. Filters are `slug`,
`lower`, `upper`, `truncate`, `replace`, `default`, `first`, and `join`.

默认 Paper Hub 模板是
`{{year}}/{{short_title|slug}}-{{paper_id}}.md`。手动导入、Form Flow 请求和
Feed 订阅都复用同一模板，因此新论文不会重新生成只有编号的正文文件；论文编号
仍保留在文件名后缀、`paper_uid` 和 aliases 中。更新已有论文时优先使用记录中已经
选定的 `note_path`，以免改名覆盖用户内容。旧的纯编号 Markdown 仅作为迁移后的
`type: paper-redirect` 兼容入口。

Expressions, attribute access, calls, absolute paths, traversal, Windows
reserved names, illegal characters, trailing dots, and overlong results are
blocked or sanitized. Use `paths variables`, `preview`, `validate`, and
`migrate --dry-run` before applying path changes.
