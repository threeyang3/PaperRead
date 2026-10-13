# 本机学习流程

Zotero 负责条目、原始 PDF 和 Reader 标注；Core 镜像标注并生成不可变 AI 分析；
Obsidian 负责个人笔记、阅读队列、复现队列和复盘。AI Markdown 展示实际已保存的
研究问题、贡献、方法、实验、结果、局限和复现条件，缺失章节不编造。

1. 在 Zotero 阅读 PDF、高亮并评论，标注自动镜像到 Core。
2. 阅读 AI Markdown，与原文的图号、页码和实验条件交叉核对。
3. 在 Obsidian 打开该论文的独立 User Note，写个人解释、可复用思路和下一步行动。
4. 用 `paperflow review create arxiv:2504.16054 --apply --vault E:/Develop/ArxivLearn`
   创建或复用独立 Review；已有内容不会被重复创建覆盖。
5. 在 Review 的“复现笔记”中记录数据、代码、环境、预期指标、实际结果和失败原因。
   在 Obsidian 更新现有 `user_reproduction_status`，由复现队列展示。
6. 用费曼问题检验理解，再在现有复盘属性中安排下一次复习。

即使 AI 没有生成费曼问题，也能显式添加个人问题：

```powershell
paperflow zotero feynman ask --paper arxiv:2504.16054 --question "请不用论文术语解释核心方法，以及哪项实验真正支持其结论。" --apply --vault E:/Develop/ArxivLearn
paperflow zotero feynman show --paper arxiv:2504.16054 --vault E:/Develop/ArxivLearn
paperflow zotero feynman answer --paper arxiv:2504.16054 --question-id <show 返回的 ID> --answer "个人答案" --vault E:/Develop/ArxivLearn
```

问题刷新只追加新问题，既有 ID 与答案保留。个人答案写入独立 User 层，
不会写回 AI Raw。AI Markdown 如果已有不同内容，呈现命令会要求人工审阅；
可显式选择一个新输出路径生成阅读预览，原文件保留。

当前代码与回归验证通过，不能据此认定用户已经完成了一次真实复现或复盘。
