# Zotero 本机环境审计

本审计由 `paperflow zotero detect` 生成。公开文档不记录用户名、绝对路径、账号或 API 密钥；完整的本机状态保存在 Vault 的 `.paperflow/state/zotero-environment.json`，该目录已被 Git 忽略。

## 当前结果

- Zotero 已安装，版本为 9.0.5。
- 检测到一个默认 Profile。
- Profile 的 `prefs.js` 明确指定了自定义数据目录；目录结构包含 `zotero.sqlite`、`storage` 和 `logs`。
- Local API 配置为启用，但本次审计时 Zotero 未运行，因此 `127.0.0.1:23119` 不可达。这不是数据库错误，启动 Zotero 后应重新运行 `paperflow zotero status`。
- 没有读取或修改 `zotero.sqlite`，没有复制、移动或删除 storage 文件。

## 可重复命令

```text
paperflow zotero detect --vault <vault>
paperflow zotero status --vault <vault>
paperflow zotero doctor --vault <vault>
```

`--redacted` 输出适合附加到公共问题报告。任何真实迁移都必须先使用独立测试 Profile、migration plan 和 dry-run；本审计没有执行写入。
