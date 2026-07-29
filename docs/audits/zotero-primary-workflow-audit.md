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
- integrations/zotero-paperflow 已提供 Zotero 9+ bootstrap：公开 Notifier 事件经过防抖后发送到认证的 loopback Core；Item Tree 状态列、Item Pane、Collection 菜单和手动分析入口已接入，插件仍不写数据库。
- “导入并分析选中论文”已形成完整主链：插件通过公开对象 API 生成元数据快照，分块上传 PDF 到 Core 的 loopback staging；Core 校验上传偏移、PDF 魔数和 SHA-256 后才写入 standalone `data/papers` 与 `documents/zotero`，之后持久化分析作业。DOI 与 arXiv 均支持。

## 当前实现与保留边界

- `PaperFlow` Collection 的创建/复用和选中条目加入已由插件公开 API 菜单完成；Core 仍只生成计划，不直接写数据库。
- item/attachment 映射已增加插件快照通道：插件通过公开对象 API 返回条目键、Collection 成员、附件键、存储模式、大小和可用 SHA-256；Core 校验后写入本地 mapping。PDF 导入由同一插件入口显式执行；未完成上传或哈希不匹配时拒绝落盘。
- 迁移计划、插件结果接收、校验和回滚清单均保持 plan/apply/verify/rollback 分层；没有对真实 Library 执行批量迁移。
- Zotero annotation mirror 已接入：插件仅通过公开 Item API 提取高亮、下划线、图片标注、评论、颜色、标签、页码、位置和删除状态，Core 写入 `.paperflow/data/annotations/zotero/<paper_uid>` 的 SYSTEM_MANAGED JSON；Obsidian 私有 Annotation Note 不被覆盖。
- Core 首次连接需要用户提供一次随机 session token；认证成功后插件建立本机设备配对。
  配对密钥保存在 Zotero 本机偏好，Core 只保存其哈希。Core 重启后插件自动换取新
  session token；没有有效配对或 session 时只显示“未连接”，不会降级为公网请求。
- Zotero-only Core 已可通过 standalone `data-root` 启动，状态、令牌、运行日志和数据不需要 Vault；默认安全 Mock Provider，以及显式配置的 Claude、Codex 和 ChatGPT Web Provider，均通过独立 staged 输入生成 AI Raw/current pointer、Zotero AI Markdown、标注镜像和 Feynman 用户数据，不会误写 Obsidian。ChatGPT Web 仍要求用户显式开启 PDF 上传许可，并复用 Vault 外的专用浏览器配置。
- Core 任务已持久化到 `state/jobs/*.json`，Zotero UI 可读取最近任务；服务重启会恢复 `queued` 任务。Provider 不可用、登录、验证码或模型菜单异常会以失败/人工接管状态返回，不会静默降级。
- standalone Core 已能把订阅 Feed 的 Raw、AI 和 Community 缓存写入独立数据根，并通过 `/community/publish-plan` 与显式确认的 `/community/publish` 生成经过隐私/哈希校验的本地 outbox；GitHub push 仍不自动执行。
- standalone 订阅同步已补齐 `Subscription Inbox`：未发现本地 Zotero mapping 的论文进入
  `data/subscriptions/inbox` 并标记 `pending-confirmation`；已关联论文标记 `linked`；
  用户确认导入或拒绝后，`imported`/`dismissed` 状态跨重复刷新保留。Zotero UI 只显示
  脱敏元数据，导入动作由插件公共对象 API 完成，不会自动下载 PDF 或覆盖 Zotero 元数据。
- Zotero UI 已提供选中标注的社区预览和二次确认发布入口；发布只生成 Core outbox，真实 GitHub push 仍由维护者/用户在独立发布流程中执行。
- 插件新增 Reader 适配和控制中心：控制中心默认以“收件箱、分析、阅读、订阅、社区”标签呈现高频操作，将连接、刷新和诊断放入“更多”；当前条目的 Reader 工作区聚合 AI 状态、标注、费曼、订阅、社区和最近任务。Core 通过只读 `/zotero/items/{item_key}/workspace`、`/subscriptions/status` 与 `/community/papers/{paper_uid}` 提供摘要，不暴露原始提示、密钥或本地路径。Item Tree 状态列覆盖 AI、阅读、复盘、复现、社区和同步。
- Connector 事件现在对 PDF 做两次公开对象快照；只有大小和 SHA-256 一致时才标记 `pdf_stable`，否则保持 `stabilizing`，避免下载尚未完成就排队分析。事件中的 `analysis_profile` 会由 Core 解析为真实 provider，作业同时保留 profile/provider/model provenance。

## 独立 Core CLI 入口（本轮新增）

### AI Markdown 附件链路

Core 通过认证的 `/zotero/markdown/<paper_uid>` 接口返回 UTF-8 渲染结果，Zotero 插件使用公开 `Zotero.Attachments.importFromFile()` 创建 Markdown 子附件。相同内容按 SHA-256 复用，不同内容生成新版本，不覆盖用户附件；Core 不写 Zotero 数据库。

Zotero-only Core 不要求存在 Obsidian Workspace。初始化后可使用以下只读或安全计划命令：

```text
paperflow zotero items --data-root <core-root> --items-json <fixture>
paperflow zotero scan --data-root <core-root>
paperflow zotero create-collection --data-root <core-root>
paperflow zotero analyze-pending --data-root <core-root>
paperflow zotero sync-status --data-root <core-root>
paperflow zotero sync-annotations --data-root <core-root>
paperflow zotero conflicts --data-root <core-root>
paperflow zotero community --data-root <core-root>
```

其中 Collection 创建、标注读取和真实 Zotero 写入始终返回 `plugin-required`，必须由 Zotero 插件通过公开对象 API 执行；Core 不打开 `zotero.sqlite`。`analyze-pending --apply` 仅在 standalone Core 中运行已配置 Provider，并写入版本化 AI Raw。

## 本轮审计证据（2026-07-28）

- 本机 Zotero 9.0.6、单一活动 Profile 和自定义数据目录已被只读探测；Zotero 启动后 Local API 可达，已完成 20 条目只读扫描和 33 篇本地论文 migration plan/dry-run，没有读取或修改 `zotero.sqlite`。
- 本机 Edge Zotero Connector 已被环境检测识别；PaperFlow 不读取浏览器凭据，Connector 到 Zotero 的导入仍由 Zotero 官方公开对象 API 接收。
- 已在源码仓库内用 Zotero `--profile`/`--headless` 创建隔离测试 Profile 并完成启动探测；该 Profile 未指向主 Profile 的自定义数据目录。两个隔离 Profile 的 `extensions.json` 已确认 PaperFlow 1.5.0 active；Collection/Reader/PDF staging 的真实对象 API E2E 仍只允许在隔离可见 Profile 中验证。
- 2026-07-28 当前工作树完整回归为 202 个 pytest 全部通过，全部 Zotero
  JavaScript 集成测试文件通过；覆盖控制中心标签、社区状态列、AI Markdown
  endpoint/附件链路、显式 ArtifactPolicy 权限枚举、秘密文件优先级、`--data-root`
  条目读取、兼容命令安全拒绝数据库写入、冲突文件只读报告、多 Profile、中文/空格
  路径和缺失数据目录。
- `ArtifactPolicy`、`PermissionGuard`、`WriteAuthorizer` 和 `PublishScanner` 现在区分 `IMMUTABLE_SOURCE`、`AI_VERSIONED`、`SYSTEM_MANAGED`、`USER_OWNED`、`USER_EDITABLE_PROJECTION`、`PUBLIC_IMMUTABLE`、`REMOTE_READ_ONLY`、`SECRET` 和 `EPHEMERAL`；系统写入不得落到用户论文/笔记目录，Feed 发布前拒绝用户文件、缓存、订阅缓存、数据库、日志和 PDF。
- `SECRET` 文件名优先于父目录分类：位于 `runtime` 或 `state` 下的 session token/
  `auth.json` 不会被降级为普通临时数据或系统状态，发布扫描会明确拒绝。
- Feynman 问题由 AI 投影，用户答案单独保存在 user-managed 文件；系统重新分析不会覆盖答案。
- 隔离 Zotero 9.0.6 Profile 已以 π0.5（`arxiv:2504.16054`）完成真实写入闭环：
  创建/复用 `PaperFlow` Collection，条目 `8XL74URF`、PDF 附件 `JV46V7IT`、
  AI Markdown 附件 `I7N92IGU` 与 mapping 一致；PDF SHA-256 为
  `6a1029fd8ab6944b74cf22f5e5d30e60bc15699d964b2900af799b807a34b64c`，
  mapping 状态为 `sha256-verified`。
- 同一隔离 Profile 的 Reader 标注 `HQQVWNGR` 已通过公开 Zotero Item API 重新镜像：
  Core 与 Vault JSON 均包含 `highlight`、原文、用户评论、页码 `1`、颜色
  `#ffd400` 以及 `pageIndex/rects` 位置。该流程不会新建旧式 Obsidian Annotation
  Note；旧文件仍按兼容策略保留。
- 分析结果已附加到 Zotero，并投影到
  `20 AI Analyses/2025/2504.16054.analysis.md`。隔离 Profile 同时启用了
  `obsidian-notepad-for-zotero@acatechnic` 1.0.0-beta.19；它是可选阅读界面，
  不是 PaperFlow 数据正确性的前置条件。
- 2026-07-27 的无持久化脱敏检测确认主 Profile 已安装并启用
  `paperflow-zotero@threeyang` 1.5.0；Zotero 当时未运行，因此 Local API 不可达，
  未对主 Library 执行 Collection、条目、附件或 Reader 写入。Edge Connector 已安装，
  但尚未作为 PaperFlow 端到端证据。真实 Collection 与 Reader 回归仍应在独立测试
  Profile 完成后再做。

## 设计决策

Zotero 作为后续主要阅读前端，Obsidian PDF 作为 Legacy / Compatibility Mode。任何写入 Zotero 的功能必须通过公开对象 API 或 PaperFlow Zotero 插件完成，绝不直接写 `zotero.sqlite`。

## 未纳入本次验收

- 主 Profile 的批量迁移或写入；本次只在隔离 Profile 创建测试对象。
- Zotero Connector 从浏览器保存网页的完整自动化验收。
- 第三方 Markdown 插件的所有主题、编辑器和双向写回组合；PaperFlow 只保证
  自己生成的 Markdown 附件与 Obsidian 主投影一致。

这些扩展验收不会改变当前边界：任何真实 Zotero 写入仍必须通过公开对象 API，
绝不直接操作 `zotero.sqlite`。
