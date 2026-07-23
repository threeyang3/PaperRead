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

- 尚未通过 Zotero 插件 API 创建或复用 `PaperFlow` Collection；Core 只生成计划，不直接写数据库。
- 尚未实现 Zotero item/attachment 映射、PDF hash 校验、migration plan/apply/rollback。
- Zotero annotation mirror 已接入：插件仅通过公开 Item API 提取高亮、下划线、图片标注、评论、颜色、标签、页码、位置和删除状态，Core 写入 `.paperflow/data/annotations/zotero/<paper_uid>` 的 SYSTEM_MANAGED JSON；Obsidian 私有 Annotation Note 不被覆盖。
- Core 会话需要用户显式复制一次令牌到 Zotero 本机偏好；没有令牌时插件只显示“未连接”，不会降级为公网请求。
- Zotero-only 模式、订阅渲染和社区发布仍以 PaperFlow/Obsidian 通道为主。

## 设计决策

Zotero 作为后续主要阅读前端，Obsidian PDF 作为 Legacy / Compatibility Mode。任何写入 Zotero 的功能必须通过公开对象 API 或 PaperFlow Zotero 插件完成，绝不直接写 `zotero.sqlite`。

## 下一阶段顺序

1. 用独立测试 Profile 验证 PaperFlow Collection 创建/复用和事件回传。
2. 实现 item identity mapping、附件 hash 验证和可回滚迁移。
3. 增加 Core job worker、Reader annotation mirror 和订阅/社区面板。

在上述能力完成并通过测试前，不会对真实 Zotero Library 执行批量迁移。
