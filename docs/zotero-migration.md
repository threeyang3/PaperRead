# Zotero 迁移计划与只读 Local API

PaperFlow 现在提供只读的 Zotero Local API 适配器和可复现迁移计划：

如果不使用 Obsidian，可以先初始化独立 Core Data Root（默认只预览）：

```text
paperflow zotero data-root --data-root D:/PaperFlowData
paperflow zotero data-root --data-root D:/PaperFlowData --apply
```

它只创建 `data/`、`documents/`、`state/`、`jobs/`、`cache/`、`backups/` 和 `logs/` 等目录，
不会移动或删除 Vault、Zotero 数据或 PDF。现有 Vault 仍使用 `.paperflow` 布局，不受影响。

```text
paperflow zotero items --items-json examples/zotero/items.example.json
paperflow zotero scan --items-json examples/zotero/items.example.json
paperflow zotero migrate plan --items-json examples/zotero/items.example.json --dry-run
paperflow zotero migrate verify
paperflow zotero migrate rollback --plan migration-plan.json
```

未提供 `--items-json` 时，`items`/`scan` 从 Workspace 配置的 loopback Local API
读取；只允许 `127.0.0.1`、`localhost` 或 `::1`，所有请求均为 GET。Zotero 未运行、API
关闭或返回非 JSON 时，命令会失败并保留可诊断错误，不会访问 `zotero.sqlite`。

`migrate plan` 会记录论文身份匹配、PaperFlow Collection、PDF 来源、附件模式和 SHA-256，
但不会创建条目、复制附件或修改 Zotero。真正写入必须由 Zotero 插件执行；插件完成后，
可以把经过校验的结果交给：

```text
paperflow zotero migrate apply --results-json plugin-results.json
```

该命令只写入 PaperFlow mapping。`rollback` 也只生成“撤销本轮 Collection membership”的
清单，不删除已有条目或 PDF。原 Vault PDF 始终保留，重复执行计划不会隐式合并不确定身份。
