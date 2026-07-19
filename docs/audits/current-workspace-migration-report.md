# 当前 Workspace 迁移报告

> 本文记录 2026-07-17 的首次产品化迁移，不代表当前论文数量或测试基线。
> 当前状态请以[验证矩阵](../verification-matrix.md)为准。
>
> Workspace：`E:/ObsidianVaults/ArxivLearn`  
> 执行时间：2026-07-17 17:00（Asia/Shanghai）  
> Migration：`workspace-0001-productization-20260717-172616-b8ef5d00`

## 迁移前

| 项目 | 数量 |
|---|---:|
| 旧混合 JSON | 2 |
| 论文笔记 | 2 |
| PDF | 2 |
| Raw Records | 0 |
| AI Records | 0 |
| User Records | 0 |

最终 dry-run 预测 2 Raw、1 AI、2 User、2 Derived，未识别字段 0，
PDF/Markdown move 0，redirect 0，网络、PDF 下载和 AI 调用均为 0。

即时备份位于 `.paperflow/backups/workspace-20260717-165825`。备份清单
记录 29 个复制文件和 2 个 PDF 的路径、大小、SHA-256；SQLite
`PRAGMA integrity_check=ok`。

## 迁移后

| 项目 | 数量 |
|---|---:|
| 旧混合 JSON（保留） | 2 |
| Raw Records | 2 |
| AI Records | 1 |
| User Records | 2 |
| Derived Records | 2 |
| 论文笔记 | 2 |
| PDF | 2 |
| 未识别 legacy 字段 | 0 |

自动迁移快照位于
`.paperflow/backups/workspace-0001-productization-20260717-172616-b8ef5d00`。
历史日志位于 `.paperflow/state/migrations/history.jsonl`，可使用 migration
ID 或 run ID 执行 rollback。

初始 run `workspace-0001-productization-20260717-170003-72aed077` 已先成功
rollback，再应用最终 Raw/AI provenance Schema；这同时验证了真实
Workspace 的回滚路径。

## 数据完整性

- `.paperflow/data/papers/arxiv_2303.04137.json`：
  `04b4ba2363d61631f3b47a04502b7ed47db2a4e56bb3ac95fcb7269e3ceab934`
- `.paperflow/data/papers/arxiv_2607.14021.json`：
  `3788fcad8a9c365cd44e3b9482a56cf1dad6877e0acc1d86523a99b15701fbd7`
- 两篇 Markdown 的迁移后哈希与即时备份一致。
- 两个 PDF 的迁移后哈希与即时备份一致：
  `b65c474b...babc8f` 和 `cc5b8fef...f1ed5d`。
- `paperflow migrate verify`：Raw=2、AI=1、User=2、Derived=2、
  SQLite=ok、links=ok。
- `paperflow paths migrate --dry-run`：move=0、redirect=0、conflict=0。

## 运行验证

- 完整 pytest：155 passed；另有 2 个 Node 调度器/控制中心生命周期集成测试通过。
- PaperFlow Automation JavaScript 调度测试通过。
- Doctor 和产品 audit 全部 PASS。
- Obsidian 正常重启成功；locale 标记由插件更新为 `zh-CN`。
- 启动 Inbox 于 2026-07-17 17:09（北京时间）完成，exit code=0。
- Windows PaperFlow 计划任务数量为 0。

迁移没有重新下载 PDF、重新提取文本、调用 AI、移动论文笔记或发布任何
远程内容。
