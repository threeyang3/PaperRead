# GitHub 社区贡献工作流

默认工作流是 fork + 专用 branch + pull request，不向上游 main force-push，
也不在 Workspace 保存 PAT。GitHub CLI 使用当前已登录身份。

本地门禁顺序：

1. 显式选择私有内容；
2. 生成不可变公共快照；
3. 展示发布预览；
4. 运行隐私、版权、Schema 和目标 PDF hash 检查；
5. 写入本地 outbox；
6. 生成 PR tree 和 diff；
7. 用户再次批准后才允许网络提交。

本轮 `paperflow community publish submit-pr` 固定为 dry-run。ArXiv-data CI
应再次检查 Schema、身份目录、目标版本/hash、HTML/URI、图片、大小和引用上限。
