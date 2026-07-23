# PaperFlow Automation

此本地 Obsidian 插件负责 PaperFlow 调度和可视化控制中心：

- Form Flow 在 `50 Inbox/Paper Requests` 创建或更新请求后，由 Obsidian
  Vault 文件事件防抖触发 Inbox；启动时和每 5 分钟轮询作为兜底。
- 每天 `Asia/Shanghai` 08:00 运行每日流程。
- 08:00 时 Obsidian 未运行，则在下次打开后补跑。
- 可按独立间隔自动同步所有明确启用的 Feed 订阅；逐源信任、禁用和移除
  均可在控制中心管理。
- 数据源主机可在一次明确授权后自动构建、验证、隐私扫描，并仅在有变化时
  commit/push 固定 origin 与分支；订阅缓存不会被再次发布。
- 可从固定 GitHub Releases 仓库自动发现并 SHA256 暂存新版本；应用升级
  始终需要确认，并先备份 Workspace、保留旧运行时、迁移和升级插件资源。
- Obsidian 工作区加载完成后默认自动打开控制中心；可在插件设置中关闭。
- 控制中心“立即执行”区域可一键运行“补齐论文图片”，通过固定白名单命令
  从本地 PDF 提取有原文图注支撑的架构图、方法总览和关键结果图。
- 命令面板、Ribbon、PDF/论文文件菜单与控制中心可创建私有 PDF 标注。若
  PDF++ 的 `copy-link-to-selection` 命令和剪贴板可用，会校验并预填真实选区；
  否则显示页码/文本表单。保存始终调用 PaperFlow CLI 并刷新标注索引。
- 阅读工作区先调用中央 `annotation ensure-index`，再打开 CLI 返回的配置路径；
  不硬编码年份或默认标注根目录。旧索引不删除，用户正文只导入一次。
- 直接启动 Vault 内固定 `.paperflow/.venv/Scripts/python.exe`，`shell: false`，不调用 PowerShell、CMD 或 Windows Task Scheduler。
- 不把笔记、表单或剪贴板内容拼接进命令行。
- Python 流水线仍使用 `.paperflow/runtime/pipeline.lock` 防止并发。
- 左侧功能区或命令面板可打开“PaperFlow 控制中心”。首屏是可扩展的独立
  任务工作台，覆盖论文收集与发现、论文库浏览、阅读/复现队列、每日回顾、
  已导入论文分析、AI profile/模型/推理强度配置与探测，不限定为三个入口，
  也不表达线性先后关系。GitHub Feed 订阅/同步、Feed 构建/验证/隐私扫描、
  Git 初始化/状态/提交及二次确认后的 push 收在“高级工具”。
- Agent 工具边界固定为 staged-only：Codex read-only sandbox，Claude
  空工具集；控制中心不允许扩大该权限。
- 控制中心只使用固定命令 allowlist 和 `shell: false`；不提供任意命令输入框。
- GitHub URL 限制为 HTTPS owner/repository 格式。订阅 clone 禁用 hooks；
  发布仓库本地 hooks 也被禁用，`.git` 永不进入 Feed 校验和或隐私扫描内容。
- Push 前后端都会再次执行 Feed 验证与隐私扫描；未选择数据许可证时无法构建。

插件只在 Obsidian 桌面版打开时运行。手动命令：

发布入口 `main.js` 已内联阅读工作区实现，不依赖运行时相对 `require()`。
即使 Electron renderer 的当前目录不在插件目录，插件也可直接加载。
阅读工作区会创建四个独立 leaf；Review 固定从 PDF leaf 分栏，最后等待并聚焦
PDF leaf，避免右侧复用或 active leaf 变化覆盖目标视图。

- `PaperFlow Automation: 立即处理 Inbox`
- `PaperFlow Automation: 立即运行每日流程`
- `PaperFlow Automation: 显示自动化状态`
- `PaperFlow Automation: 打开控制中心`
- `PaperFlow Automation: 从当前 PDF / 选区创建标注`
