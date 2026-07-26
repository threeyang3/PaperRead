# Zotero 本机环境审计

本审计由 `paperflow zotero detect` 生成。公开文档不记录用户名、绝对路径、账号或 API 密钥；完整的本机状态保存在 Vault 的 `.paperflow/state/zotero-environment.json`，该目录已被 Git 忽略。

## 当前结果

- Zotero 已安装，版本为 9.0.6（2026-07-26 重新只读检测）。
- 检测到一个默认 Profile。
- Profile 的 `prefs.js` 明确指定了自定义数据目录；目录结构包含 `zotero.sqlite`、`storage` 和 `logs`。
- Local API 配置为启用；Zotero 运行中时 `127.0.0.1:23119` 可达（HTTP 200）。返回的根路径文本为 Zotero 的正常占位响应，随后通过 `users/0/items` 只读条目查询已成功。
- 当前主 Profile 的 `paperflow-zotero@threeyang` 未安装且未 active；Edge Connector 已安装，但 Connector 不等同于桌面端 PaperFlow 插件。环境检测现在会明确报告 `paperflow_plugin.installed/active`。
- 没有读取或修改 `zotero.sqlite`，没有复制、移动或删除 storage 文件。
- Edge 已发现 Zotero Connector（扩展 ID `nmhdhpibnnopknkmonacoephklnflpho`）；检测只读取扩展 manifest 的版本信息，不读取浏览器历史、Cookie 或登录态。

## 可重复命令

```text
paperflow zotero detect --vault <vault>
paperflow zotero status --vault <vault>
paperflow zotero doctor --vault <vault>
```

`--redacted` 输出适合附加到公共问题报告。任何真实迁移都必须先使用独立测试 Profile、migration plan 和 dry-run；本审计没有执行写入。

`paperflow zotero status` 和 `paperflow zotero doctor` 还会分别报告
`ready_for_plugin_integration` 以及 PaperFlow 插件的 `installed/active` 状态；Local API
可达不代表桌面端插件已经安装。

## 证据边界

- 已确认：Windows 11、单一默认 Profile、自定义数据目录存在、`zotero.sqlite`、`storage`、`logs` 存在、Local API 配置启用、Edge Zotero Connector 已安装。
- 已确认：Zotero 启动后的真实 Local API 请求、20 条目只读扫描和 33 篇本地论文迁移 dry-run 均成功；未执行任何 Zotero 写入。
- 未确认：Connector 导入、Reader 标注事件和 PaperFlow XPI 在可见隔离 Profile 中的端到端 UI 流程；这些需要在隔离 Profile 手动安装插件后验证。
- 安全保证：本命令不打开 `zotero.sqlite`，不复制/移动/删除 Zotero storage，网络探测仅限 loopback。
