# Zotero 主阅读工作流差距审计

## 已有能力

- PaperFlow Core 已将 Raw、AI、User、Derived、Community 数据分层保存。
- Obsidian PDF、PDF++、Annotation Note、PDF backlink 和阅读工作区继续保留为兼容模式。
- 论文文件名已迁移为“短标题-编号”，旧路径保留 redirect，避免断链。
- Topic、Method、Dataset 关系已分层生成；同一类型内的大小写、空格和连字符变体可归一化。
- `paperflow zotero detect/status/doctor` 已能只读检测安装、Profile、自定义 data directory 和 loopback Local API。
- Workspace 已加入 `zotero`/`integrations` 配置：默认 Collection 名为 `PaperFlow`、分析触发策略为 `collection_only`，附件默认 `stored` 且保留原 PDF。
- 已提供 loopback-only Core 服务（`paperflow zotero service start/status/stop`），服务只接受显式 API 路由并使用每次启动的 bearer 会话令牌。
- `paperflow zotero link --items-json ...` 可根据 Zotero 插件/API 导出的 JSON 生成身份映射 dry-run；仅 arXiv/DOI 精确匹配可自动写入，标题候选仍需人工复核。
- integrations/zotero-paperflow 已提供 Zotero 7/9 bootstrap：公开 Notifier 事件经过防抖后发送到认证的 loopback Core；Item Tree 状态列、Item Pane、Collection 菜单和手动分析入口已接入，插件仍不写数据库。

## 当前缺口

- `PaperFlow` Collection 的创建/复用和选中条目加入已由插件公开 API 菜单完成；Core 仍只生成计划，不直接写数据库。
- item/attachment 映射已增加插件快照通道：插件通过公开对象 API 返回条目键、Collection 成员、附件键、存储模式、大小和可用 SHA-256；Core 校验后写入本地 mapping。真实文件导入仍必须由插件显式执行，未提供哈希时保持 `pending-file-check`。
- 迁移计划、插件结果接收、校验和回滚清单均保持 plan/apply/verify/rollback 分层；没有对真实 Library 执行批量迁移。
- Zotero annotation mirror 已接入：插件仅通过公开 Item API 提取高亮、下划线、图片标注、评论、颜色、标签、页码、位置和删除状态，Core 写入 `.paperflow/data/annotations/zotero/<paper_uid>` 的 SYSTEM_MANAGED JSON；Obsidian 私有 Annotation Note 不被覆盖。
- Core 会话需要用户显式复制一次令牌到 Zotero 本机偏好；没有令牌时插件只显示“未连接”，不会降级为公网请求。
- Zotero-only Core 已可通过 standalone `data-root` 启动，状态、令牌、运行日志和数据不需要 Vault；没有 Workspace 的 standalone Core 只提供安全队列/读取，不会误写 Obsidian。
- Core 任务已持久化到 `state/jobs/*.json`，Zotero UI 可读取最近任务；服务重启会恢复 `queued` 任务，依赖 Vault pipeline 的 standalone 分析会明确记录 `skipped / workspace-not-configured`，不产生假成功。
- 订阅渲染和社区发布仍以 PaperFlow/Obsidian 通道为主，Zotero 面板目前提供本地 Core 队列和发布预览，尚未静默写入远端。

## 本轮审计证据（2026-07-23）

- 本机 Zotero 9.0.5、单一活动 Profile 和自定义数据目录已被只读探测；Zotero 未启动时 Local API 不可达被正确报告为“未启动”，没有读取或修改 `zotero.sqlite`。
- PaperRead 当前分支完整 pytest 169 个用例全部通过，5 组 Node 插件/Core 集成测试全部通过。
- 新增 `ArtifactPolicy`、`PermissionGuard`、`WriteAuthorizer` 和 `PublishScanner`：系统写入不得落到用户论文/笔记目录，Feed 发布前拒绝用户文件、数据库、日志和 PDF。
- Feynman 问题由 AI 投影，用户答案单独保存在 user-managed 文件；系统重新分析不会覆盖答案。
- 当前真实主 Profile 的 extensions 目录未发现 PaperFlow Zotero 插件 XPI；本轮只完成源码、模拟对象和 Core loopback 验证，没有未经确认地改写主 Profile。安装/真实 Collection 与 Reader 回归应在独立测试 Profile 完成后再做。

## 设计决策

Zotero 作为后续主要阅读前端，Obsidian PDF 作为 Legacy / Compatibility Mode。任何写入 Zotero 的功能必须通过公开对象 API 或 PaperFlow Zotero 插件完成，绝不直接写 `zotero.sqlite`。

## 下一阶段顺序

1. 在独立测试 Profile 验证 PaperFlow Collection 创建/复用、附件导入和 Reader 事件回传。
2. 将已有 migration plan/apply/verify/rollback 在测试 Profile 跑通，并把真实文件 hash 从 pending 提升为 verified。
3. 继续把订阅/社区面板和 standalone Core 的完整 AI worker 接入 Zotero UI；Obsidian 仍只保留兼容模式。

在上述能力完成并通过测试前，不会对真实 Zotero Library 执行批量迁移。
