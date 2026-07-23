# 社区隐私与版权

每个贡献在进入 outbox 和 PR tree 前都执行 fail-closed 扫描。阻止：

- `user_*`、个人笔记边界和绝对/用户目录路径；
- token、cookie、密码、API key、PAT 和邮箱；
- script/iframe/object/embed/style、事件处理器和危险 URI；
- 图片、PDF、Data URI 和可执行内容；
- 超过 64 KiB 的贡献或超过 500 字符的来源引用。

论文全文、PDF、图片、完整页面选择和本地 Derived 资产从不发布。贡献者必须
确认自己有权发布评论与有限引用，并在确认页查看 GitHub 身份、许可、引用、
评论、标签、评分、目标仓库/分支和具体文件。

PaperFlow 不替用户选择新的公开许可。本项目软件继续使用 MIT；现有
ArXiv-data 的 CC BY 4.0 保持不变。
