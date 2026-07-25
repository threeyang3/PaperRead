# Zotero UI 集成

插件在 Zotero 提供以下公开 API 适配：

- Item Tree 状态列：AI、阅读、复盘、复现、同步。
- Item Pane 的 PaperFlow 区域，显示同一组高频状态。
- `Notifier` 的 item add/modify/delete 防抖队列，默认等待 10 秒合并事件；可通过 Zotero 偏好 `extensions.paperflow-zotero.eventDebounceMs` 调整，且事件只把 PDF 附件视为可分析输入。
- 条目上下文菜单中的“将选中论文加入 Collection”。
- 条目上下文菜单中的“同步身份与附件校验”：通过公开对象 API 生成 mapping 快照，Core 只写本地 mapping，不写 Zotero 数据库。
- 条目上下文菜单中的“连接 Core”和“导入并分析选中论文”。该命令先通过 Zotero
  公开对象 API 读取元数据和 PDF 附件，分块发送到已认证的本机 Core staging，
  Core 校验 PDF 头和 SHA-256 后才写入 standalone canonical data，再排队分析。
  Core 地址与会话令牌只保存于
  Zotero 本机偏好设置；令牌来自被忽略的 `.paperflow/runtime` 配对命令。
- “同步订阅预览”和“预览选中标注的社区发布”菜单。前者只创建本机 Core 队列项；
  后者从选中的 Zotero 标注生成经过隐私/锚点校验的计划。另有独立的“确认发布选中
  标注”菜单，二次确认后只写入本机 outbox，不会自动 push GitHub，也不会写入 Zotero
  数据库。
- “查看订阅 Inbox”显示远端新增但尚未进入 Zotero 的论文。订阅同步只保存脱敏元数据和
  PDF 来源信息，不会自动创建条目或下载 PDF；选择一条记录后用“确认导入订阅论文”
  才会通过 Zotero 公共对象 API 创建/复用 bibliographic item、加入 PaperFlow
  Collection，并把 Inbox 状态标记为 imported。拒绝或稍后处理的决定会跨刷新保留。
- “查看状态”会读取 Core 的最近任务状态；分析、渲染和订阅任务在 Core state/jobs
  中持久化，服务重启后仍可恢复 queued 任务，不依赖 Zotero 回调窗口保持打开。
- Zotero 标注事件会镜像到 Core 的 SYSTEM_MANAGED 数据层，并在 Item Pane 显示当前论文
  的有效镜像数量；镜像删除不会删除 Zotero 或旧 Obsidian 标注。

状态列只读取本地缓存或认证 Core 返回的状态；Core 不可用时显示占位符，不会在每一行实时
启动 Python、AI 或公网请求。事件只提交公开条目键、附件键和身份提示，分析由 Core worker
在 pipeline lock 下执行。不同 Zotero 版本缺少 Item Tree/Item Pane API 时，插件
仅跳过对应 UI 并保留其他功能，不修改 Zotero DOM，也不访问数据库。

PDF 暂存只接受 loopback bearer 请求；Core 不接收 Zotero 文件系统路径、不打开
`zotero.sqlite`，分块偏移、大小、PDF 魔数和 SHA-256 任一不匹配都会拒绝并删除临时片段。
已有同哈希 PDF 会复用；不同哈希不会覆盖旧文件，而是生成 `manual-review` 冲突副本。

订阅 Inbox 的数据位于 Core 数据根的 `data/subscriptions/inbox/`（Vault 兼容模式为
`.paperflow/data/subscriptions/inbox/`），属于 `REMOTE_READ_ONLY`。Zotero UI 只接收
公开元数据，不暴露本地源文件路径、校验哈希或浏览器配置；导入后的 mapping 仍由 Core
保存，Zotero 条目的 bibliographic 字段不会被远端订阅覆盖。
