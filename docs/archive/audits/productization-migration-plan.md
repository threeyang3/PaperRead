# 当前 Workspace 产品化迁移计划

> 本文是 2026-07-17 已完成迁移的历史计划。当前维护流程请参阅
> [用户与维护者指南](../../维护者与用户指南.md)。
>
> 状态：已完成 apply、verify 和运行时验证  
> 基线备份：`.paperflow/backups/productization-20260717-151342`

## 迁移目标

把两个旧混合 JSON 非破坏地拆分为不可变 Raw、追加式 AI 和本地 User sidecar，同时保留旧 JSON、Markdown、PDF、请求和简报。

## 计划步骤

1. 建立标准程序包和版本契约，不触碰当前数据。
2. 实现正式 migration registry、plan、apply、verify、rollback、history。
3. 扫描两个旧 JSON、两篇 Markdown、两个 PDF 和 SQLite。
4. 为每个输入计算 SHA-256，并把未知字段放入 `extensions.legacy`。
5. 在 `.paperflow/migrations/staging/<run-id>` 生成：
   - `.paperflow/data/raw/<source>/<paper-id>/v<version>.json`
   - `.paperflow/data/ai/<profile>/<paper-id>/v<version>/<analysis-id>.json`
   - `.paperflow/data/user/<paper-uid>.yaml`
   - `.paperflow/data/derived/` 索引
6. 验证 Schema、数量、内容哈希、用户字段和用户笔记哈希。
7. 原子提交新文件；不覆盖或删除 `.paperflow/data/papers`。
8. 写入 migration history 和逐文件输入/输出哈希。
9. 验证 SQLite、wikilink、Bases、Form Flow 和 Obsidian 自动化。
10. rollback 只移除本次新增的分层文件并恢复迁移前索引；旧文件始终保留。

## 当前 dry-run 预估

| 项目 | 数量 |
|---|---:|
| 输入旧 JSON | 2 |
| 计划 Raw Records | 2 |
| 计划 AI Records | 1（另 1 篇尚未分析） |
| 计划 User sidecars | 2 |
| PDF 移动 | 0 |
| Markdown 移动 | 0 |
| redirect | 0 |
| 预计重新下载 PDF | 0 |
| 预计重新提取文本 | 0 |
| 预计 AI 调用 | 0 |

正式 apply 只能在程序化 `paperflow migrate plan` 输出与本计划一致、备份完整性验证通过后执行。

## 实际执行

- dry-run 与上表完全一致，`destructive_overwrites=0`。
- 即时备份：`.paperflow/backups/workspace-20260717-165825`，29 个复制文件及 2 个 PDF 哈希条目，SQLite `integrity_check=ok`。
- 初始 run `workspace-0001-productization-20260717-170003-72aed077` 已成功 rollback，用于验证可逆性。
- 最终 run：`workspace-0001-productization-20260717-172616-b8ef5d00`。
- 结果：2 Raw、1 AI、2 User、2 Derived，unknown fields=0。
- 网络请求=0、PDF 下载=0、AI 调用=0、Markdown/PDF 移动=0。
- verify：Schema、数量、SQLite、note path 和 legacy 文件均通过。
- Obsidian 正常重启后 PaperFlow Automation Inbox 成功，exit code=0。
