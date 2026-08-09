# 私有标注与论文评审

个人标注位于 `60 Annotations`，论文评审位于 `60 Reviews`；机器 sidecar 位于
`.paperflow/data/user/annotations`。三者都属于私有 User 层，不进入 Feed。

## 标注

Zotero 主阅读模式下，Zotero Reader 标注是 USER_OWNED 真源，Core 只在
`.paperflow/data/annotations/zotero/<paper_uid>/` 保存 SYSTEM_MANAGED 的只读
JSON 镜像。新 Zotero 标注不会生成新的 Obsidian Annotation Note；下面的 Markdown
协议适用于 Obsidian/PDF++ 兼容模式和历史标注，两种来源不会互相覆盖。

标注支持 highlight、passage-comment、question、critique、figure-comment、
section-comment、paper-review 和 rating。每条记录保存：

- PDF 版本、SHA-256、Vault 相对路径和页码；
- FragmentSelector；
- 可选 TextQuoteSelector、TextPositionSelector 和矩形；
- 可选 PDF++ 四元组 selection 与显示颜色；二者不等同于引用文本；
- 所选文本 SHA-256；
- 不可变 anchor revisions，其中恰好一个为 preferred。

Markdown 是人可读、可编辑真源，JSON 是可重建 sidecar。双方均发生修改时，
PaperFlow 停止覆盖并要求 Manual Review。边界外的未知 Markdown 和
`extensions` 元数据会保留。

标注笔记的阅读视图使用简洁投影：文件路径和机器属性仍用于稳定链接与审计，
但正文只显示中文标注类型、原文摘录和“打开 PDF · 第 N 页”；PDF++ 的 selection
四元组、哈希和重定位状态保留在隐藏属性/机器区块中。

Annotation Schema 仍为 v1：`pdf_selection` 与 `highlight_color` 是向后兼容的
可选 anchor 字段，不需要 Workspace 迁移。旧版本将自由文本放进 `selection=`
的记录仍可读取，但重新渲染时只输出页码；实际引用文本保留在
`TextQuoteSelector`，不会生成无效 PDF 选区。

```powershell
paperflow annotation list
paperflow annotation validate
paperflow annotation sync --dry-run
paperflow annotation ensure-index arxiv:2504.16054 --apply
paperflow workspace rebuild-annotation-index --apply
paperflow annotation create arxiv:2504.16054 `
  "[[80 Attachments/Papers/2025/2504.16054/v1.pdf#page=5]]" `
  --kind question --motivation questioning `
  --selected-text "actual visible text" --body "Why?" --apply
```

每篇论文的可见索引位于 Workspace 配置的标注根目录下，默认是
`60 Annotations/arxiv_2504.16054/index.md`。阅读工作区通过中央 CLI 获取该
路径，不再假定 `年份/paper_id`。重建索引只替换
`PAPERFLOW_ANNOTATION_INDEX_START/END` 之间的机器区块，保留 frontmatter
扩展和区块外的用户正文。

旧版年份目录中的 `index.md` 不会被删除或改写。若其中包含非标准骨架的用户
正文，首次重建会带来源标记导入规范索引；再次运行不会重复导入。单条标注仍
以 Markdown 为真源，索引只是可重建投影。

## 评审

评审包含摘要、优点、局限、问题、复现笔记、结论和可选 1–5 个人评分。
个人评分不会与 AI 分数或社区评分合并。

```powershell
paperflow review create arxiv:2504.16054 --rating 5 --vault "D:\Notes\Research"
paperflow review validate
```

`review create` 默认真正创建 Review；重复执行会返回 `existing`，保留原始
`review_id` 和文件字节，不覆盖已经写下的复盘。只有预览时才传 `--dry-run`，
此时返回 `would-create`。已有 Review 无法解析时命令进入 Manual Review 并拒绝
覆盖。
