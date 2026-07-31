# Zotero 写入测试边界

真实主 Profile 未被用于写入测试。2026-07-28 已在
`E:\PaperRead\var\zotero-dev-profile` 隔离 Profile 中，通过 Zotero 公开对象 API
创建/复用 Collection 与测试条目、导入 PDF/Markdown 附件并同步 Reader 标注；
全过程没有访问 `zotero.sqlite`。

Zotero 9.0.6 的正式发行版会识别源码 proxy 文件，但不会像开发版一样自动启用未打包
的源码扩展；这不是 PaperFlow 的运行时错误。可复现的隔离测试入口是：

```powershell
python scripts/build_release.py
.\scripts\zotero-e2e.ps1 -Reset -Launch
```

脚本只允许 `E:\PaperRead\var` 下的 Profile，并强制把隔离 Zotero data directory 设置在该
Profile 的 `zotero-data` 子目录；不会回落到用户主 Profile 的自定义数据目录。脚本在 Zotero 窗口中提示通过“工具 -> 插件
-> 齿轮 -> 从文件安装插件”选择构建出的 XPI。完成安装并重启后，脚本会读取该隔离
Profile 的 `extensions.json`，要求 `paperflow-zotero@threeyang` 为 active 且没有
`userDisabled/appDisabled`；它不会读取或修改主 Profile 的数据库。Edge 中已安装的
Zotero Connector 可继续把 arXiv 页面保存到 Zotero，但 Connector 不会替代这一步的
Zotero 桌面插件安装。

执行真实迁移前，应启动独立测试 Profile，运行 `detect`、迁移 `plan` 和 dry-run，确认
备份与回滚清单后，再通过 Zotero 插件显式执行。插件返回的 item、attachment 和
collection keys 交给 `zotero migrate apply` 只写入 PaperFlow mapping；回滚只撤销本轮
新增的 membership/测试对象，不删除迁移前已有数据或原 Vault PDF。

本机 Zotero 为 9.0.6。早期隔离实验曾因旧 XPI 清单/ZIP 路径问题显示通用“不兼容”
提示；该结论已被后续 1.5.0 构建取代。2026-07-28 的 π0.5 闭环结果：

- `PaperFlow` Collection 创建/复用成功；
- bibliographic item `8XL74URF`、PDF `JV46V7IT` 与 AI Markdown
  `I7N92IGU` 已创建并写入同一 mapping；
- PDF SHA-256 校验状态为 `sha256-verified`；
- 分析进入 Core 作业流水线，Zotero AI Markdown 与 Obsidian 主投影均存在；
- Reader 标注 `HQQVWNGR` 已镜像原文、评论、页码、颜色和位置；
- 首次配对后，隔离 Zotero 可在 Core 重启时自动续期 session；
- PaperFlow 1.5.0 与可选的 Obsidian Notepad for Zotero
  1.0.0-beta.19 均在该 Profile 中 active。

主 Profile 的脱敏检测只确认插件安装/启用，没有执行 Collection、条目、附件或
Reader 写入。不得通过修改 `extensions.json`、直接复制 XPI 到主 Profile 或触碰
主数据目录来绕过安装流程。
