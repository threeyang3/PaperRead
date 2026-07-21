# 社区贡献

个人标注默认私有。只有 `community select` 显式选择的内容才会生成不可变公开
快照。快照包含 GitHub 身份、内容许可、论文/PDF 版本哈希、有限引用、评论、
标签、可选评分和内容哈希，不包含个人原始笔记或本地路径。

```powershell
paperflow community list
paperflow community preview <snapshot.json>
paperflow community select <private-selection.json> \
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
