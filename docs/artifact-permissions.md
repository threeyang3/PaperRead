# PaperFlow 数据权限

PaperFlow 不再只根据目录名称判断“能否写入”。Core 的写入器使用
`ArtifactPolicy` 为每个路径映射到明确的权限类别，并在写入前调用
`PermissionGuard`。旧的 `SYSTEM_MANAGED`/`USER_MANAGED` 判断仍保留，供旧插件和
旧数据兼容。

| 类别 | 典型路径 | 规则 |
| --- | --- | --- |
| `IMMUTABLE_SOURCE` | `data/raw`、`documents/zotero` 中的 PDF | 只能追加来源新版本，不覆盖旧内容 |
| `AI_VERSIONED` | `data/ai` | 只能追加新的分析 revision，并更新 current 指针 |
| `SYSTEM_MANAGED` | `data/annotations`、`state`、模板 | 由 Core/插件维护，用户不直接编辑 |
| `USER_OWNED` | `data/user`、个人笔记、复盘和复现 | 系统不得覆盖 |
| `USER_EDITABLE_PROJECTION` | `20 AI Analyses`、Zotero AI Markdown | 用户可以编辑；重新渲染发现差异时必须进入 Manual Review |
| `PUBLIC_IMMUTABLE` | `data/community/outbox` | 发布前确认，写入后不可变 |
| `REMOTE_READ_ONLY` | 订阅缓存 | 用户不可编辑，刷新可替换本地缓存 |
| `EPHEMERAL` | `runtime`、`cache`、`logs` | 不进 Feed、Git 或发布物，可清理 |
| `SECRET` | token、认证文件和环境文件 | 绝不发布或写入同步内容 |

Feed、社区和发布物在写出前通过 `PublishScanner` 检查用户文件、缓存、日志、数据
库、PDF、token 和订阅缓存。任何不确定路径都不会被自动纳入发布物。
秘密文件名的判定优先于父目录：即使 token 或 `auth.json` 位于 `runtime`、`state`
等系统目录，也必须保持 `SECRET`，不能降级为普通临时文件或系统状态。

`USER_OWNED` 的含义包括“缺失时可按用户动作创建，存在时不得覆盖”。因此论文
首次导入可以创建标准 User Note，`review create` 可以创建 Review；重复执行、
分析、刷新和渲染必须原样保留已有 User Note、Review、Annotation、`user_*` 和
用户标签。无法安全解析或合并时进入 Manual Review，不以空模板替换。

## 端职责

- Zotero bibliographic data、PDF 和 Zotero Annotation 仍由 Zotero 公开对象 API 主导。
- Annotation Mirror、AI Raw、状态和订阅缓存由 Core 管理。
- AI Markdown 是可编辑投影；个人笔记、费曼答案、复盘和复现记录永不被 AI 更新覆盖。
- Obsidian PDF 与旧 Annotation Note 保留为兼容模式，迁移和导出不会删除原文件。
