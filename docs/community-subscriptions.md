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

屏蔽作者与隐藏贡献位于本地
`.paperflow/data/user/community-preferences.yaml`，不会发布。把社区引用复制为
个人标注必须是显式用户操作。
