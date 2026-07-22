# PaperFlow 显示标题、独立笔记与模板系统审计

审计日期：2026-07-22（Asia/Shanghai）  
源码版本：PaperFlow 1.5.0，分支 `agent/paperflow-1.5`，基线提交 `384e26b`。

## 审计结论

当前版本已经具备分层数据、HTML 优先图片、PDF++ 标注、社区发布/订阅和紧凑论文模板，但本轮计划要求的“友好标题与独立 Paper Workspace”尚未完成。最重要的结构性缺口是：论文主文档仍同时承担 Hub、AI 正文和用户笔记三个角色；用户笔记只通过 `USER_NOTES_START/END` 标记保存在主文档中；模板仍由单个 locale 文件选择，尚无可管理的 Template Set 和沙箱。

## 当前实现矩阵

| 能力 | 当前状态 | 证据/风险 | 本轮处理 |
|---|---|---|---|
| 稳定 ID 路径 | 已有 | 默认 `10 Papers/{{year}}/{{paper_id}}.md`，现有路径稳定 | 保持默认不改名，补充显示字段和可选短标题变量 |
| 来源/显示标题 | 部分 | `paper_title_display` 与基本 aliases 已有；没有 `short_title`、用户覆盖和完整 alias 规则 | 增加 Derived/用户投影、别名合并和安全路径变量 |
| Paper Hub | 部分 | `10 Papers` 论文文档包含摘要/分析正文，未形成独立导航层 | 将主文档收敛为 Hub，提供稳定 artifact 链接 |
| AI Analysis Note | 缺失 | `20 AI Analyses` 不存在 | 新增独立生成文档和路径规则 |
| User Note | 缺失 | 用户内容位于主文档 `USER_NOTES_START/END`，另有 `.paperflow/data/user` sidecar | 新增 `60 User Notes`，提供 dry-run/apply/verify/rollback 迁移 |
| Annotation/Review/Community | 已有 | `60 Annotations`、`60 Reviews`、`70 Community` 已具备 canonical 路径/索引 | 接入 Hub 链接，保留既有兼容逻辑 |
| PDF artifact | 已有 | `80 Attachments/Papers`，PDF++ link 可用 | 接入 Hub/context，不改变用户附件路径 |
| Paper View Model | 缺失 | renderer 直接向 Jinja 暴露合并 record | 新增 context version、稳定嵌套 view model 与兼容 flat keys |
| Template Set | 缺失 | `Paper Note Template(.en).md` 单文件选择 | 新增内置/自定义 set、copy/list/use/show/validate/preview/import/export/diff/doctor |
| 模板安全 | 不足 | 当前使用普通 `jinja2.Environment` | 改为受限 `SandboxedEnvironment`，禁止路径穿越和危险属性 |
| 迁移/备份 | 部分 | 既有 workspace/migrations；没有用户笔记迁移 | 新增正式迁移、manifest、校验和人工复核 |
| UI | 部分 | Control Center 已有 Agent、Feed、发布和维护卡片 | 增加 Workspace artifacts、Template Set 与用户笔记迁移入口 |
| Bases/仪表盘 | 部分 | 动态 Bases 已有 | 投影 `display_title`、artifact links 和关系字段，避免依赖文件名 |

## 兼容与安全边界

- Raw/AI 不可变记录不覆盖；标题修复只进入 Derived/用户投影。
- 不自动覆盖 `user_*`、用户 tags 或 `USER_NOTES_START/END`；迁移遇到目标已修改、哈希不符或缺少标记时生成 Manual Review。
- 默认不批量重命名现有论文文件；`id-only` 是稳定默认策略，短标题只作为显示和可选新路径变量。
- 模板预览不得写入 Vault、调用网络或读取模板根目录之外的文件。
- 本轮不修改远端分支、PR 或 ArXiv-data；完成本地测试和构建后再由用户另行决定发布。

## 实施顺序

1. 补齐显示标题/short title/用户覆盖及 aliases，保持 ID 路径兼容。
2. 增加 Paper Hub、AI Analysis Note、User Note 路径与生成器。
3. 提供 USER_NOTES 正式迁移（备份、dry-run、apply、verify、rollback）。
4. 引入稳定 Paper View Model 和 Sandboxed Jinja Template Set 管理。
5. 更新 Obsidian 控制中心、Bases、文档、迁移测试和打包审计。

## 基线

`pytest --collect-only -q` 当前收集 126 个测试；后续每个代码变更均运行完整测试集、插件生命周期测试和构建检查。
