# Obsidian 阅读工作区

先打开一篇 PaperFlow 论文笔记，再执行命令面板：

```text
PaperFlow: Open paper reading workspace
```

插件打开：

- 左侧：当前版本 PDF；
- 右上：该论文标注索引；
- 右下：个人 Review；
- 右侧附加页：只读 Community Note。

插件为四个目标使用四个独立 leaf。Review 明确以 PDF leaf 为锚点创建水平分栏，
不会因当前 active leaf 改变而丢失；标注与 Community 使用不同的右侧 leaf。
全部文件打开后，插件等待 PDF leaf 完成 reveal，并把焦点切回 PDF。

打开布局前，插件通过中央 allowlist 调用
`paperflow annotation ensure-index <paper_uid> --apply`，并使用 JSON 返回的
实际路径。默认索引是 `60 Annotations/<paper_id>/index.md`；若 Workspace
配置了其他标注根目录，则完全服从配置。旧版
`60 Annotations/<year>/<paper_id>/index.md` 保留不动，其中的用户正文只会
带来源标记导入一次。

缺少标注、Review 或 Community Note 时，插件只创建私有/派生骨架，不创建公共
贡献。控制中心提供“阅读、标注、评审、社区、发布贡献”五个并列入口；它们与
抓取、分析和 Agent 设置没有前后继关系。

Ribbon、命令面板、PDF/论文文件菜单和控制中心都提供“创建 PDF 标注”。安装
PDF++ 时，一键入口优先运行其 Copy link to selection 命令并预填表单；否则
明确退化到页码、所选文本和评论表单。高亮、评论、问题和批评均由 PaperFlow
CLI 中央写入 User 层，并立即刷新 `60 Annotations` 索引；不会直接修改 PDF。

标注链接固化 selector、PDF 版本和 SHA-256。历史 PDF 仍可打开；切换版本不会
静默改写标注，需通过 revision/reanchor 流程定位新版本。

## 论文文件名与实体目录

Paper Hub 的物理文件名采用“短标题-论文编号”形式，例如
`10 Papers/2025/π₀.₅-2504.16054.md`。编号仍是唯一身份，并继续写入
`paper_uid`、`paper_arxiv_id` 和 aliases；因此文件改名不会改变 Raw、AI、User、
Derived 或 PDF 的身份。旧 Vault 必须先执行
`paperflow migrate readable-paper-paths` 预览，再使用 `--apply` 执行迁移。
迁移会备份 Workspace、保留旧路径重定向、重写 Vault 内 wikilink，并重新渲染
论文关系；不会覆盖用户属性或 `USER_NOTES_START/END`。

`20 Topics` 根目录表示宽泛研究主题；`20 Topics/Methods` 表示方法实体，
`20 Topics/Datasets` 表示数据集实体。相同词出现在 Topic 和 Method 两层是
类型投影，不等于同一文件；同一层内仅保留一个规范 slug。旧版因空格/连字符或
旧 YAML 格式产生的重复实体，可先用 `paperflow migrate entities` 检查，确认后
使用 `paperflow migrate entities --apply` 合并。旧文件会先备份，链接会改指向
规范实体；含有非生成正文的文件不会自动删除，而会列入人工复核。

因此 `Diffusion Policy` 在 Topic 和 Method 两层各有一个文件是有意保留的：前者
表示研究主题，后者表示方法关系。它们的 `type`/`entity/*` 标签不同，图谱不会把
两种边混成一类；实体页会在正文顶部明确显示“主题/方法”类型，并列出反向论文；
但同一层的 `Diffusion Policy`、`Diffusion-Policy` 或大小写变体
不应并存。当前库已完成 `entities-0001` 合并，并通过
`paperflow migrate entity-labels --apply` 将方法笔记标题统一为读者友好的
`Diffusion Policy`（旧 slug 仍作为路径兼容，正文和别名不会丢失）。

论文迁移后留下的纯编号 Markdown 是 `type: paper-redirect` 兼容入口，不是第二份论文正文。
它们现在会显示“已迁移：<论文标题>”并提供“打开论文笔记”链接；可用
`paperflow migrate redirect-labels --apply` 补充旧入口，带有用户自定义正文的入口会进入
`manual_review` 而不会被覆盖。更多示例见 [主题、方法与数据集实体](entity-navigation.md)。
