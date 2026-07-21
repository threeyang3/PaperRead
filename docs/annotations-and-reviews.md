# 私有标注与论文评审

个人标注位于 `60 Annotations`，论文评审位于 `60 Reviews`；机器 sidecar 位于
`.paperflow/data/user/annotations`。三者都属于私有 User 层，不进入 Feed。

## 标注

标注支持 highlight、passage-comment、question、critique、figure-comment、
section-comment、paper-review 和 rating。每条记录保存：

- PDF 版本、SHA-256、Vault 相对路径和页码；
- FragmentSelector；
- 可选 TextQuoteSelector、TextPositionSelector 和矩形；
- 所选文本 SHA-256；
- 不可变 anchor revisions，其中恰好一个为 preferred。

Markdown 是人可读、可编辑真源，JSON 是可重建 sidecar。双方均发生修改时，
PaperFlow 停止覆盖并要求 Manual Review。边界外的未知 Markdown 和
`extensions` 元数据会保留。

```powershell
paperflow annotation list
paperflow annotation validate
paperflow annotation sync --dry-run
paperflow workspace rebuild-annotation-index --apply
```

## 评审

评审包含摘要、优点、局限、问题、复现笔记、结论和可选 1–5 个人评分。
个人评分不会与 AI 分数或社区评分合并。

```powershell
paperflow review create arxiv:2504.16054 --rating 5 --dry-run
paperflow review validate
```
