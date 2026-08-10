# Paper Workspace：论文 Hub、AI 分析与用户笔记

AI 分析快照的属性只保存可检索的标量与来源信息（摘要、推荐、评分、Provider、
模型、Prompt 版本和时间）；正文只保留问题、贡献、方法、实验、结果、局限和
关系等解释性内容。阅读建议和 AI 来源不会在同一快照正文重复出现，Paper Hub
只呈现一次面向读者的阅读建议。用户修改 Paper Hub 或 `60 User Notes` 不会改写
该快照，也不会改变已发布 Feed 的 AI 文件。

PaperFlow 现在把一篇论文拆成可独立维护的工作区对象：

- `10 Papers/<年份>/<短标题>-<论文 ID>.md`：稳定的 Paper Hub，适合打开论文、查看摘要和导航；历史 ID-only 文件保留为重定向入口。
- `20 AI Analyses/<年份>/<论文 ID>.analysis.md`：AI 分析快照，重新分析不会覆盖用户笔记。
- `60 User Notes/<年份>/<论文 ID>.notes.md`：用户自己的观察、疑问、思路和行动。
- `60 Annotations`、`60 Reviews`、`70 Community`：标注、复盘和社区贡献。

每次成功导入都会幂等地确保 `60 User Notes` 中存在独立 User Note，即使关闭
AI 或 AI 尚未成功也一样。Form Flow 的“我的笔记”直接写入这里，不再先写进
Paper Hub 再用字符串替换迁移。重复导入、分析、刷新和渲染都只能链接或合并
这些 USER_OWNED artifact，不得重建或覆盖它们。

新导入论文使用短标题与 arXiv ID 组合的可读文件名，标题变化时沿用记录中的既有路径；历史 ID-only 文件不删除，只作为兼容重定向。显示标题使用 `paper_display_title`（可由用户 `user_display_title` 覆盖），`paper_short_title` 也用于路径模板；原始标题和 arXiv ID 会保留在 aliases。

## 用户笔记迁移

```powershell
paperflow workspace backup --vault "E:\ObsidianVaults\ArxivLearn"
paperflow migrate user-notes --vault "E:\ObsidianVaults\ArxivLearn" --dry-run
paperflow migrate user-notes --vault "E:\ObsidianVaults\ArxivLearn" --apply
```

迁移会保留 Workspace backup 和 `.paperflow/backups/user-notes-*`。旧论文 Hub 不会被删除；目标已存在时会报告冲突并跳过该篇。

## 模板集

```powershell
paperflow templates list --vault "E:\ObsidianVaults\ArxivLearn"
paperflow templates validate --vault "E:\ObsidianVaults\ArxivLearn"
paperflow templates copy academic-zh --destination my-reading --vault "E:\ObsidianVaults\ArxivLearn"
paperflow templates use my-reading --vault "E:\ObsidianVaults\ArxivLearn"
```

自定义模板只能使用 Paper View Model；预览不调用网络、不写入 Vault。Jinja sandbox 禁止路径穿越和危险对象属性访问。维护者可用 `paperflow paper view-model arxiv:2504.16054` 检查 context version。
