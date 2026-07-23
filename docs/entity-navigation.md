# 主题、方法与数据集实体

PaperFlow 将论文关系拆成三类实体，以便在 Obsidian 图谱中区分“研究方向”和“实现方法”：

- `20 Topics/`：宽泛研究主题，例如 Robot Manipulation、Diffusion Policy。
- `20 Topics/Methods/`：论文中可复用的算法、训练或控制方法。
- `20 Topics/Datasets/`：数据集、评测基准和数据资源。

因此 `20 Topics/Diffusion-Policy.md`（`type: topic`）与
`20 Topics/Methods/Diffusion-Policy.md`（`type: method`）不是同一层的重复文件：
前者回答“论文属于什么研究主题”，后者回答“论文采用了什么方法”。它们可以在图谱中
分别承接 `ai_topic_links` 和 `ai_method_links` 两种边。实体页会显示“实体类型”和规范键，
并在“相关论文”区维护反向论文索引；打开实体页即可看到它实际关联的论文。

实体标题统一使用读者友好的显示名；空格、连字符、下划线和大小写差异在同一层会被
`paperflow migrate entities` 合并。`paperflow migrate entity-labels` 只调整显示标题和
别名，不改变已有路径或正文。

旧版本实体页缺少反向论文列表时，可先预览再应用：

```powershell
paperflow migrate entity-index --vault "E:\\ObsidianVaults\\ArxivLearn" --dry-run
paperflow migrate entity-index --vault "E:\\ObsidianVaults\\ArxivLearn" --apply
```

该命令只更新 `PAPERFLOW_ENTITY_INDEX_START/END` 标记之间的生成区块，保留实体页其余
正文；论文记录仍是唯一事实来源。

论文文件名使用“短标题-arXiv ID”格式，例如 `π₀.₅-2504.16054.md`。迁移后保留的纯
编号文件是旧路径兼容入口（`type: paper-redirect`），不含论文正文；可以打开它的链接
跳转到可读文件。使用 `paperflow migrate redirect-labels --apply` 可将旧入口补充为明确的
“已迁移”提示；带有用户自定义正文的入口会列入 `manual_review`，不会被覆盖。
