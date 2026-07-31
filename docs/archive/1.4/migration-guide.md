# PaperFlow 1.4 迁移指南

> 历史文档：仅用于维护仍停留在 PaperFlow 1.4 的旧 Workspace。当前安装、
> 升级和迁移流程请从 [文档导航](../../README.md) 进入。

1. 关闭正在执行的 PaperFlow 作业，等待同步软件稳定。
2. 检查冲突：`paperflow health`。
3. 预览：`paperflow migrate workspace-v2 --dry-run`。
4. 应用：`paperflow migrate workspace-v2 --apply`。
5. 验证：

   ```powershell
   paperflow migrate verify-workspace-v2
   paperflow paper validate
   paperflow doctor
   paperflow audit
   ```

迁移升级 Workspace schema 2 和模板 v5，安装 ChatGPT Web Provider、图片/关系设置与同步兼容设置，并使用四层合成器重渲染已生成论文。它保留旧 Raw/AI 记录、`user_*`、用户标签和 `USER_NOTES_START/END`。

回退时使用迁移输出中的 `.paperflow/backups/pre-paperflow-1.4-*`。先停止插件，再从备份恢复受影响文件；不要用 Git 覆盖用户笔记。
