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
`publishing.include_community_contributions=false`。`submit-pr` 当前只输出
fork→branch→commit→PR 计划和完整文件清单，不发生网络写入。真实 PR 需要另一次
明确授权。

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

默认远程流程是 fork → 专用 branch → pull request，不向上游 `main`
force-push，也不在 Workspace 保存 PAT。提交前必须依次完成：

1. 显式选择私有内容并生成不可变快照；
2. 展示发布预览；
3. 校验隐私、版权、Schema、内容哈希和目标 PDF hash；
4. 写入本地 outbox 并生成 PR tree/diff；
5. 用户再次授权后才允许网络提交。

`paperflow community publish submit-pr` 当前只生成计划；ArXiv-data CI 会再次
验证身份目录、Schema、哈希、HTML/URI、文件类型、大小和引用上限。
