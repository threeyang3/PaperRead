# PaperFlow for Zotero

这是 PaperFlow 的 Zotero 7/9 集成。它把 Zotero 条目、Collection 和 Reader 作为主要阅读
入口，同时把分析任务交给本机 loopback Core，而不是替代 Zotero Reader：

- 只使用 Zotero 公开的 bootstrap、Notifier 和菜单 API；
- 不读取或修改 `zotero.sqlite`；
- 不复制、移动或删除 Zotero storage；
- 事件观察器经过 1 秒防抖后，仅发送公开条目字段到已认证的 loopback Core；Core 再决定是否满足 Collection、PDF 和身份条件，插件回调中不会运行 AI；
- Item Tree 状态列、Item Pane、PaperFlow Collection 和“分析选中论文”菜单均已接入。

插件的“PaperFlow：查看状态”菜单只探测 loopback Core 的 /health，不会把 Zotero 数据发送到公网。论文数据接口仍要求 PaperFlow 会话令牌；令牌只保存于 Zotero 本机偏好设置，不写入插件源码、Vault 或 Zotero 数据库。

在 PaperFlow Core 中先运行：

```text
paperflow zotero detect
paperflow zotero doctor
paperflow zotero service start --vault <vault>
paperflow zotero service token --vault <vault>
paperflow zotero service status --vault <vault>
```

首次连接：复制 service token 输出的令牌，在 Zotero 条目菜单选择“PaperFlow：连接 Core”，输入 http://127.0.0.1:23140 和令牌。令牌文件位于被忽略的 .paperflow/runtime，停止 Core 后自动删除；不要把令牌提交到 Git 或同步到其他设备。之后可在 Zotero 中选择“PaperFlow：分析选中论文”手动排队分析。自动事件仅携带条目键、附件键、Collection/PDF 存在性和 arXiv/DOI 身份提示，Core 仍会在真正分析前重新校验。

如果只使用 Zotero、不启用 Obsidian，可先建立独立 Core 数据根并启动服务：

```text
paperflow zotero data-root --data-root <core-data-root> --apply
paperflow zotero service start --data-root <core-data-root>
paperflow zotero service token --data-root <core-data-root>
```

standalone Core 使用 `data/`、`state/`、`runtime/` 等目录，不会创建或扫描 Obsidian Vault；没有 Workspace 配置时只提供安全队列和本地镜像。
分析、渲染和订阅请求会写入 `state/jobs/*.json`，任务状态可通过“查看状态”菜单或
认证的 `/jobs`、`/jobs/{job_id}` 读取；Core 重启会恢复仍为 `queued` 的任务。没有
Workspace 的 standalone 根会明确将依赖 Vault pipeline 的分析任务标记为
`skipped / workspace-not-configured`，不会伪称分析成功。

Zotero Reader 的高亮、下划线、图片标注和评论以只读镜像形式保存到
`.paperflow/data/annotations/zotero/<paper_uid>/`，镜像由 Core 统一写入并带有
`SYSTEM_MANAGED` 权限；不要手动编辑这些 JSON。删除的 Zotero 标注只标记 deleted，不会
删除旧 Obsidian 私有标注。

可以先用脱敏 fixture 生成映射计划（不会访问 Zotero 数据库）：

```text
paperflow zotero link --items-json examples/zotero/items.example.json --vault <vault>
paperflow zotero link --items-json examples/zotero/items.example.json --vault <vault> --apply
```

真实 Zotero Library 写入必须经过测试 Profile、migration plan、dry-run 和用户确认。

“同步身份与附件校验”菜单会把选中条目的公开 API 快照发送到已认证的 loopback Core，包含附件键、存储模式和可用 SHA-256，不包含本机路径。Core 校验通过后才写入 mapping；文件复制/链接仍由 Zotero 插件公开附件 API 执行。

发布构建会生成 `PaperFlow-Zotero-1.5.0.xpi`。本轮没有自动安装到真实主 Profile；请先在独立测试 Profile 安装并完成 Collection、Reader 和附件回归，再由用户确认安装到主 Profile。
