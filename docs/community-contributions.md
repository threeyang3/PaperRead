# 社区贡献

个人标注默认私有。只有 `community select` 显式选择的内容才会生成不可变公开
快照。快照包含 GitHub 身份、内容许可、论文/PDF 版本哈希、有限引用、评论、
标签、可选评分和内容哈希，不包含个人原始笔记或本地路径。

`select` 只接受当前 Vault 中 PaperFlow 管理的私有标注 JSON 或 Review Markdown，
不会读取任意外部文件。标注的本地 PDF 路径、矩形坐标、PDF++ 选区字符串和
高亮插件状态在投影时全部移除；公开锚点只保留 PDF 版本/哈希、页码及受长度
限制的引用上下文。内容哈希在默认字段补齐后的最终公开结构上计算。

```powershell
paperflow community list
paperflow community preview <snapshot.json>
paperflow community select <private-annotation.json-or-review.md> \
  --creator <github-user> --license <chosen-license> --dry-run
paperflow community publish plan
paperflow community publish scan
paperflow community publish build <candidate-dir> --dry-run
paperflow community publish submit-pr
```

发布默认关闭：`community.publish_enabled=false` 且
`publishing.include_community_contributions=false`。`submit-pr` 默认生成只读预览，
包含目标仓库、所选文件、许可、文件 SHA-256 和整个预览的 `plan_sha256`。
只有 `--apply --confirm-digest <预览哈希>` 才能进入真实提交，且三个发布开关
`publishing.enabled`、`community.publish_enabled`、
`publishing.include_community_contributions` 都必须开启。

修改已发布内容会创建 r2 并通过 `supersedes` 指向 r1；撤回使用独立 retraction
记录，不删除 Git 历史。

Feed 订阅启用 `community` capability 后，会把通过哈希和隐私校验的记录写入
只读 cache，并在 `70 Community/<year>/<paper_id>.community.md` 生成可见聚合
笔记。该过程不会修改 User 层或 AI 层。

公开数据与本地 Markdown 隔离：Feed 的 AI 分析只读取
`.paperflow/data/ai`，社区贡献只读取显式 outbox。用户随后编辑论文 Markdown、
私有标注或 Review，都不会改变已经生成的公开快照；要发布修改必须显式创建
新 revision。

## GitHub 提交流程

当前个人仓库模式使用专用 branch → 草稿 pull request。源码仓库为
`threeyang3/PaperRead`，数据和社区贡献仓库为 `threeyang3/ArXiv-data`。
模式为 owner-only：快照 creator 和经过 GitHub `/user` 验证的当前账号都必须
匹配目标仓库所有者；还必须有目标仓库的 push 权限。连接到某个 GitHub 账号
不等于其有权以另一位 creator 的身份提交。公开 fork 投稿和组织 Team 授权
尚未实现。
本机 owner-only 校验约束 PaperFlow 提交器；公共仓库的外部 PR
仍由 GitHub 仓库权限、CI 和所有者审阅处理。

提交不更新默认分支、不自动合并、不保存 PAT 到 Workspace。提交前必须依次完成：

1. 显式选择私有内容并生成不可变快照；
2. 展示发布预览；
3. 校验隐私、版权、Schema、内容哈希和目标 PDF hash；
4. 写入本地 outbox 并生成 PR tree/diff；
5. 用户再次授权后才允许网络提交。

CLI 提交从进程环境 `GH_TOKEN` 或 `GITHUB_TOKEN` 获取认证，Codex GitHub 连接
不会自动把它的凭据传给 Python CLI。不要把 token 写进配置、文档或命令行参数。
账号验证和所有预检完成后，提交器冻结预览批准的字节，创建不可变 blob/tree/commit
及确定命名的专用分支，再创建草稿 PR。提交同时维护对应 Community manifest
和 Feed checksum，保留其他已有记录；预览的 `derived_files` 列出这些索引文件。
目标须为已初始化的 PaperFlow Feed。相同远端 revision 内容不同就停止，
需创建新 revision；部分失败后再次运行会复用内容相同的已有分支和 PR。
若文件已在默认分支原样存在，返回 `already-published`。

```powershell
paperflow community publish submit-pr --vault E:/Develop/ArxivLearn
# 审阅所选快照及上一步返回的哈希后，才执行：
paperflow community publish submit-pr --apply --confirm-digest <plan_sha256> --vault E:/Develop/ArxivLearn
```

隐私校验覆盖正文、标签、anchor 上下文和嵌套 extensions，避免隐藏的路径、
凭据或 user_* 字段越过公开边界。ArXiv-data CI 再验证仓库侧约束。
