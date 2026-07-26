# Zotero 写入测试边界

当前实现只在模拟 Zotero 对象上验证了公共 Collection API。真实主 Profile 未被用于写入
测试，因此本轮没有创建真实 Collection、条目或附件，也没有访问 `zotero.sqlite`。

Zotero 9.0.6 的正式发行版会识别源码 proxy 文件，但不会像开发版一样自动启用未打包
的源码扩展；这不是 PaperFlow 的运行时错误。可复现的隔离测试入口是：

```powershell
python scripts/build_release.py
.\scripts\zotero-e2e.ps1 -Reset -Launch
```

脚本只允许 `E:\PaperRead\var` 下的 Profile，并强制把隔离 Zotero data directory 设置在该
Profile 的 `zotero-data` 子目录；不会回落到用户默认的 Zotero 数据目录。脚本在 Zotero 窗口中提示通过“工具 -> 插件
-> 齿轮 -> 从文件安装插件”选择构建出的 XPI。完成安装并重启后，脚本会读取该隔离
Profile 的 `extensions.json`，要求 `paperflow-zotero@threeyang` 为 active 且没有
`userDisabled/appDisabled`；它不会读取或修改主 Profile 的数据库。Edge 中已安装的
Zotero Connector 可继续把 arXiv 页面保存到 Zotero，但 Connector 不会替代这一步的
Zotero 桌面插件安装。

执行真实迁移前，应启动独立测试 Profile，运行 `detect`、迁移 `plan` 和 dry-run，确认
备份与回滚清单后，再通过 Zotero 插件显式执行。插件返回的 item、attachment 和
collection keys 交给 `zotero migrate apply` 只写入 PaperFlow mapping；回滚只撤销本轮
新增的 membership/测试对象，不删除迁移前已有数据或原 Vault PDF。

本机 Zotero 为 9.0.6。2026-07-26 的隔离 Profile 实验中，官方“从文件安装插件”对最小
manifest.json + bootstrap.js 探针和 PaperFlow XPI 都返回通用的“可能无法与该版本兼容”提示，
extensions.json 仍为 addons: []；因此当前不能宣称桌面插件已安装。最新 XPI 已按 Zotero 9
清单格式构建（根目录含 manifest.json、bootstrap.js、prefs.js，兼容范围为 9.0–9.0.*，
不含 install.rdf）。这项 UI 安装阻塞不影响 Local API 只读扫描，也不应通过直接复制 XPI 或修改
D:\\Zotero 来绕过。待 Zotero 官方安装器接受该 XPI 后，再继续 Collection、Reader、PDF staging
和标注镜像的真实 E2E 验证。
