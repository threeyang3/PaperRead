# Paper Workspace：论文 Hub、AI 分析与用户笔记

PaperFlow 现在把一篇论文拆成可独立维护的工作区对象：

- `10 Papers/<年份>/<论文 ID>.md`：稳定的 Paper Hub，适合打开论文、查看摘要和导航。
- `20 AI Analyses/<年份>/<论文 ID>.analysis.md`：AI 分析快照，重新分析不会覆盖用户笔记。
- `60 User Notes/<年份>/<论文 ID>.notes.md`：用户自己的观察、疑问、思路和行动。
- `60 Annotations`、`60 Reviews`、`70 Community`：标注、复盘和社区贡献。

论文文件名默认仍只使用稳定 ID，避免标题变化造成断链。显示标题使用 `paper_display_title`（可由用户 `user_display_title` 覆盖），`paper_short_title` 只用于界面和可选路径模板；原始标题和 arXiv ID 会保留在 aliases。

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
