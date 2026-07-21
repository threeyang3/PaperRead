# PDF 版本与不可变性

默认路径：

```text
80 Attachments/Papers/<year>/<paper_id>/v<version>.pdf
```

下载后的 PDF 以版本寻址，不在 refresh 时覆盖。每篇论文的索引位于
`.paperflow/data/derived/pdf-index/<paper_uid>.json`，记录版本、路径、
SHA-256、大小和当前版本。Raw 记录中的内容哈希与该 PDF 对应。

论文笔记指向最新版本；旧标注继续指向旧 PDF。升级版本不会静默改变 anchor，
必须运行：

```powershell
paperflow annotation reanchor arxiv:2504.16054 \
  --from-version 1 --to-version 2 --dry-run
```

无法可靠匹配时生成
`50 Inbox/Manual Review/Annotation Reanchor/` 任务，旧 anchor 永久保留。
