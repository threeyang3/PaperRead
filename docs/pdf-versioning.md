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

Workspace v3 同时更新聚合论文记录和实际参与 `compose_record()` 的 Derived PDF
路径，再重渲染正文及 `#page=N` 链接。视觉 PNG 路径保持不变；manifest v1 的
`pdf_sha256` 也不因同一 PDF 被复制到 vN 路径而改变。
