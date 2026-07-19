# Nutstore Sync 兼容建议

PaperFlow 将 Nutstore Sync 视为“可能随时修改文件”的外部写入者，不修改其插件代码、全局 API 或设置。

建议在同步规则中排除：

- `.paperflow/runtime`
- `.paperflow/cache`
- `.paperflow/logs`
- `.paperflow/state/*.lock`
- SQLite 的 `-wal`、`-shm`
- 浏览器配置目录（默认已在 Vault 外）

论文笔记、PDF、Derived 图片、用户数据和实体笔记可以正常同步。若出现 `-冲突` 或 `-NSConflict` 文件，先完成冲突合并再恢复 PaperFlow 作业。PaperFlow 在写入前会复核原文件哈希；冲突时不覆盖任一方，而是在 `50 Inbox/Manual Review` 保存待合并内容。
