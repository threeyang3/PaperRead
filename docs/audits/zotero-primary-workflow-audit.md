# Zotero 主阅读工作流差距审计

## 已有能力

- PaperFlow Core 已将 Raw、AI、User、Derived、Community 数据分层保存。
- Obsidian PDF、PDF++、Annotation Note、PDF backlink 和阅读工作区继续保留为兼容模式。
- 论文文件名已迁移为“短标题-编号”，旧路径保留 redirect，避免断链。
- Topic、Method、Dataset 关系仅作为兼容性导航索引保留，不是 Zotero 主工作流的前置步骤，也不参与论文导入、PDF 阅读或 AI 分析。
- `paperflow zotero detect/status/doctor` 已能只读检测安装、Profile、自定义 data directory 和 loopback Local API。
- Workspace 已加入 `zotero`/`integrations` 配置：默认 Collection 名为 `PaperFlow`、分析触发策略为 `collection_only`，附件默认 `stored` 且保留原 PDF。
- 已提供 loopback-only Core 服务（`paperflow zotero service start/status/stop`），服务只接受显式 API 路由并使用每次启动的 bearer 会话令牌。
- `paperflow zotero link --items-json ...` 可根据 Zotero 插件/API 导出的 JSON 生成身份映射 dry-run；仅 arXiv/DOI 精确匹配可自动写入，标题候选仍需人工复核。
- integrations/zotero-paperflow 已提供 Zotero 7/9 bootstrap：公开 Notifier 事件经过防抖后发送到认证的 loopback Core；Item Tree 状态列、Item Pane、Collection 菜单和手动分析入口已接入，插件仍不写数据库。
- “导入并分析选中论文”已形成完整主链：插件通过公开对象 API 生成元数据快照，分块上传 PDF 到 Core 的 loopback staging；Core 校验上传偏移、PDF 魔数和 SHA-256 后才写入 standalone `data/papers` 与 `documents/zotero`，之后持久化分析作业。DOI 与 arXiv 均支持。

## 当前缺口

- `PaperFlow` Collection 的创建/复用和选中条目加入已由插件公开 API 菜单完成；Core 仍只生成计划，不直接写数据库。
- item/attachment 映射已增加插件快照通道：插件通过公开对象 API 返回条目键、Collection 成员、附件键、存储模式、大小和可用 SHA-256；Core 校验后写入本地 mapping。PDF 导入由同一插件入口显式执行；未完成上传或哈希不匹配时拒绝落盘。
- 迁移计划、插件结果接收、校验和回滚清单均保持 plan/apply/verify/rollback 分层；没有对真实 Library 执行批量迁移。
- Zotero annotation mirror 已接入：插件仅通过公开 Item API 提取高亮、下划线、图片标注、评论、颜色、标签、页码、位置和删除状态，Core 写入 `.paperflow/data/annotations/zotero/<paper_uid>` 的 SYSTEM_MANAGED JSON；Obsidian 私有 Annotation Note 不被覆盖。
- Core 会话需要用户显式复制一次令牌到 Zotero 本机偏好；没有令牌时插件只显示“未连接”，不会降级为公网请求。
- Zotero-only Core 已可通过 standalone `data-root` 启动，状态、令牌、运行日志和数据不需要 Vault；默认安全 Mock Provider，以及显式配置的 Claude、Codex 和 ChatGPT Web Provider，均通过独立 staged 输入生成 AI Raw/current pointer、Zotero AI Markdown、标注镜像和 Feynman 用户数据，不会误写 Obsidian。ChatGPT Web 仍要求用户显式开启 PDF 上传许可，并复用 Vault 外的专用浏览器配置。
- Core 任务已持久化到 `state/jobs/*.json`，Zotero UI 可读取最近任务；服务重启会恢复 `queued` 任务。Provider 不可用、登录、验证码或模型菜单异常会以失败/人工接管状态返回，不会静默降级。
- standalone Core 已能把订阅 Feed 的 Raw、AI 和 Community 缓存写入独立数据根，并通过 `/community/publish-plan` 与显式确认的 `/community/publish` 生成经过隐私/哈希校验的本地 outbox；GitHub push 仍不自动执行。
- standalone 订阅同步已补齐 `Subscription Inbox`：未发现本地 Zotero mapping 的论文进入
  `data/subscriptions/inbox` 并标记 `pending-confirmation`；已关联论文标记 `linked`；
  用户确认导入或拒绝后，`imported`/`dismissed` 状态跨重复刷新保留。Zotero UI 只显示
  脱敏元数据，导入动作由插件公共对象 API 完成，不会自动下载 PDF 或覆盖 Zotero 元数据。
- Zotero UI 已提供选中标注的社区预览和二次确认发布入口；发布只生成 Core outbox，真实 GitHub push 仍由维护者/用户在独立发布流程中执行。

## 本轮审计证据（2026-07-24）

- 本机 Zotero 9.0.5、单一活动 Profile 和自定义数据目录已被只读探测；Zotero 未启动时 Local API 不可达被正确报告为“未启动”，没有读取或修改 `zotero.sqlite`。
- 已在源码仓库内用 Zotero `--profile`/`--headless` 创建隔离测试 Profile 并完成启动探测；该 Profile 未指向真实 `D:\\Zotero`。由于 headless 启动不会通过安装向导加载未签名 XPI，插件实际安装/Reader 对象 API E2E 仍待用户在独立可见 Profile 中手动安装验证，未触碰主 Profile。
- PaperRead 当前分支完整 pytest 全部通过，5 组 Node 插件/Core 集成测试全部通过；新增覆盖元数据导入、PDF 分块 staging、SHA-256 拒绝、DOI 路径和订阅 Inbox 首次/重复同步。
- 新增 `ArtifactPolicy`、`PermissionGuard`、`WriteAuthorizer` 和 `PublishScanner`：系统写入不得落到用户论文/笔记目录，Feed 发布前拒绝用户文件、数据库、日志和 PDF。
- Feynman 问题由 AI 投影，用户答案单独保存在 user-managed 文件；系统重新分析不会覆盖答案。
- 当前真实主 Profile 的 extensions 目录未发现 PaperFlow Zotero 插件 XPI；本轮只完成源码、模拟对象和 Core loopback 验证，没有未经确认地改写主 Profile。安装/真实 Collection 与 Reader 回归应在独立测试 Profile 完成后再做。

## 设计决策

Zotero 作为后续主要阅读前端，Obsidian PDF 作为 Legacy / Compatibility Mode。任何写入 Zotero 的功能必须通过公开对象 API 或 PaperFlow Zotero 插件完成，绝不直接写 `zotero.sqlite`。

## 下一阶段顺序

1. 在独立测试 Profile 验证 PaperFlow Collection 创建/复用、PDF staging 导入和 Reader 事件回传。
2. 将已有 migration plan/apply/verify/rollback 在测试 Profile 跑通，并把真实文件 hash 从 pending 提升为 verified。
3. 把 standalone Core 的订阅/社区 Feed worker 接入 Zotero UI，并在独立测试 Profile 完成端到端验证；Obsidian 仍只保留兼容模式。
4. Topic/Method/Dataset 只做必要的兼容性迁移和断链修复，不再扩展其导航模型，直到上述主线验收完成。

在上述能力完成并通过测试前，不会对真实 Zotero Library 执行批量迁移。
