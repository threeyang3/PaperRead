# 社区订阅与 Obsidian 投影

Feed v1 被解释为 `raw=true, ai=true, community=false`。Feed v2 通过
capabilities 独立声明 Raw、AI 和 Community；旧订阅默认仍只请求 Raw/AI。

社区记录验证 Schema、manifest、身份命名空间和隐私规则，并按发布端相同的
canonical JSON 规则重新计算 `content_sha256`；正文、标签、评分、anchor、许可
或扩展字段发生任何未签名改动都会拒绝摄取。验证通过后才写入：

```text
.paperflow/data/community/subscriptions/<feed_id>/...
```

它们随后投影为 `70 Community/<year>/<paper_id>.community.md`，不会写入
User Annotation、Review、`user_*` 或 AI。社区评分只显示 count、median、
distribution、min/max、creator 数和更新时间；样本少于 5 时显示警告。

## 阅读界面

Community 笔记是面向读者的摘要视图：标题显示论文显示名，贡献类型使用中文
（高亮、段落评论、疑问、批评、评分等），原文摘录只保留一段简短引用，并提供
“打开 PDF · 第 N 页”的链接。贡献 ID、修订号、许可证等机器信息放在可折叠的
“贡献信息”区；YAML 属性和原始文件名默认在阅读视图中隐藏，但仍保留在文件中
供校验和审计使用。

个人标注采用相同的投影方式：正文显示“标注 · 类型”、原文摘录和 PDF 页链接，
不会把 `selection=...` 等 PDF++ 技术参数直接展示给读者。

屏蔽作者与隐藏贡献位于本地
`.paperflow/data/user/community-preferences.yaml`，不会发布。把社区引用复制为
个人标注必须是显式用户操作。
