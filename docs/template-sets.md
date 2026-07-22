# PaperFlow Template Sets

Template Set 是带 `manifest.json` 的版本化目录，声明 locale、context version 和模板文件列表。内置 `academic-zh` 与 `academic-en` 只读；用户副本位于 `.paperflow/templates/sets`。

模板只应依赖稳定的 Paper View Model（`context_version: 1`）。不要在模板中读取 `.paperflow`、调用网络或执行脚本。`templates preview` 只生成 stdout 预览；`templates validate/doctor` 会检查清单、路径穿越和 context 版本。

公共 Feed 只发布 Raw/AI/Derived 的不可变快照，不发布 `60 User Notes` 或用户在 Hub 中的本地修改。
