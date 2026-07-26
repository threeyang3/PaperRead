# PaperFlow for Zotero

这是 PaperFlow 的 Zotero 7/9 集成。它把 Zotero 条目、Collection 和 Reader 作为主要阅读
入口，同时把分析任务交给本机 loopback Core，而不是替代 Zotero Reader：

- 只使用 Zotero 公开的 bootstrap、Notifier 和菜单 API；
- 不读取或修改 `zotero.sqlite`；
- 不复制、移动或删除 Zotero storage；
- 事件观察器默认等待 10 秒（可在 Zotero 偏好中用 `extensions.paperflow-zotero.eventDebounceMs` 调整）再发送公开条目字段到已认证的 loopback Core；Core 再决定是否满足 Collection、真实 PDF 和身份条件，插件回调中不会运行 AI；
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

standalone Core 使用 `data/`、`state/`、`runtime/` 等目录，不会创建或扫描 Obsidian Vault；
默认使用安全 Mock Provider，也可在 `config.yaml` 中显式选择 Claude、Codex 或 ChatGPT Web。
外部 Provider 只接收 staged 文本/PDF；ChatGPT Web 还要求 `allow_pdf_upload: true`，
并使用 Vault 外的专用浏览器配置目录。
分析、渲染和订阅请求会写入 `state/jobs/*.json`，任务状态可通过“查看状态”菜单或
认证的 `/jobs`、`/jobs/{job_id}` 读取；Core 重启会恢复仍为 `queued` 的任务。如果
外部 Provider 不可用、登录、验证码或模型选择失败，会明确拒绝并记录原因，不会伪称分析成功；
ChatGPT Web 的网页会话仍需要用户在专用浏览器配置中完成首次登录。

standalone 订阅源写在 Core `config.yaml` 的 `subscriptions.sources` 中，例如：

```yaml
subscriptions:
  sources:
    - name: ArXiv-data
      url: https://github.com/threeyang3/ArXiv-data.git
      branch: main
      trust: metadata-and-ai
      capabilities: [raw, ai, community]
      auto_download_pdf: false
      auto_render_notes: true
```

Zotero 菜单的“同步订阅预览”只排队任务；Core 会把远端数据写入独立
`data/raw`、`data/ai` 和 `data/community` 缓存。社区发布必须先走
`/community/publish-plan`，再由用户明确确认 `/community/publish`；后者只生成
`data/community/outbox` 的不可变记录，返回 `network_changes: 0`，不会自动 push GitHub。

当订阅论文尚未关联 Zotero 条目时，Core 另外写入
`data/subscriptions/inbox/<paper-id>.json`。Zotero 中选择“查看订阅 Inbox”可查看待确认
记录；只有用户选择“确认导入订阅论文”后，插件才通过 Zotero 公共对象 API 创建或复用
条目、加入可配置的 `PaperFlow` Collection，并写入 mapping。该步骤默认只导入元数据，
不自动下载 PDF；`pending-confirmation`、`imported` 和 `dismissed` 决定会在后续同步中
保留，远端刷新不会覆盖用户决定。

Zotero Reader 的高亮、下划线、图片标注和评论以只读镜像形式保存到
standalone 的 `data/annotations/zotero/<paper_uid>/`（Vault 模式为
`.paperflow/data/annotations/zotero/<paper_uid>/`），镜像由 Core 统一写入并带有
`SYSTEM_MANAGED` 权限；不要手动编辑这些 JSON。删除的 Zotero 标注只标记 deleted，不会
删除旧 Obsidian 私有标注。

可以先用脱敏 fixture 生成映射计划（不会访问 Zotero 数据库）：

```text
paperflow zotero link --items-json examples/zotero/items.example.json --vault <vault>
paperflow zotero link --items-json examples/zotero/items.example.json --vault <vault> --apply
```

真实 Zotero Library 写入必须经过测试 Profile、migration plan、dry-run 和用户确认。

“同步身份与附件校验”菜单会把选中条目的公开 API 快照发送到已认证的 loopback Core，包含附件键、存储模式和可用 SHA-256，不包含本机路径。Core 校验通过后才写入 mapping；文件复制/链接仍由 Zotero 插件公开附件 API 执行。

发布构建会生成 `PaperFlow-Zotero-1.5.0.xpi`。XPI 使用 Zotero 7+ 的
`manifest.json`（不是 `install.rdf`），并且 ZIP 成员路径固定为 `/`。但是 Zotero 9
要求 applications.zotero.update_url、插件 ID 和兼容版本字段完整；缺少 update_url
时“从文件安装”会报告插件不兼容。当前 XPI 是未签名源码构建包，但在 Zotero 9.0.6
隔离 Profile 中已验证可被扫描并启用。Windows 下使用反斜杠打包还会导致 Zotero 将
资源解析失败，因此构建脚本已固定使用 POSIX 路径。

建议的 Zotero 9 安装流程：

1. 开发测试优先使用官方 Extension Proxy，而不是把源码复制进用户 Profile：
   `scripts\zotero-dev-profile.ps1 -Reset -Launch`。脚本只允许 Profile 位于
   `E:\PaperRead\var`，并将 `extensions\paperflow-zotero@threeyang` 指向本仓库
   的解包源码；它不会复制、删除或修改主 Profile。
2. 在隔离 Zotero 中打开“工具 → 插件”，确认插件 ID 为
   `paperflow-zotero@threeyang`，再运行 `paperflow zotero doctor`。
3. 生产安装可在 Zotero 的“工具 → 插件 → 从文件安装插件”中选择 XPI；若仍提示
   “不兼容”，先确认使用的是重新构建的包（包含 update_url）以及 Zotero 版本在
   strict_min_version/strict_max_version 范围内。不要编辑 extensions.json、关闭签名
   校验或复制 XPI 到主 Profile。
4. `scripts\zotero-e2e.ps1` 仍保留为人工 XPI/隔离 Profile 流程；它不会修改主
   Profile，并会把安装失败与插件运行时失败分开记录。

本轮没有自动安装到真实主 Profile；真实库仍保持未写入。
