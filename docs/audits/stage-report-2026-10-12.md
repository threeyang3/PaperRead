# PaperFlow 阶段报告

报告日期：2026-10-12，Asia/Shanghai。

## 阶段结论

项目已完成主要功能实现，进入本机真实场景验收和稳定化阶段。迁移后的
Obsidian 工作区已恢复运行，发现、每日简报、订阅与更新检查均可执行。
当前机器的已有论文真实 AI 分析、Zotero 导入和 Reader 标注闭环已验收；
新论文完整流程、最新设置作业界面和社区远程投稿仍待验收，
因此不能认定所有用户流程已完成端到端验收。

本报告依据当前代码、验证矩阵、2026-10-12 本机运行记录及注明日期的历史验收。
“已实现”表示代码与测试存在；“本机验证”表示迁移后的当前机器实际执行成功。
未把历史隔离环境结果当作本机主 Profile 验收结果。

## 架构与当前版本

| 组成 | 职责 | 当前状态 |
| --- | --- | --- |
| PaperFlow Core | 身份、版本、处理任务、AI、数据层、订阅与投影 | 应用 1.5.1，源码 E:/Develop/PaperRead |
| Obsidian | 论文 Hub、知识关联、AI 阅读、独立个人笔记、复盘与复现 | 1.14.4，Vault E:/Develop/ArxivLearn |
| Zotero | 文献条目、Collection、PDF 阅读及 Reader 标注真源 | 9+ 插件已实现，本机主 Profile 尚待验收 |
| Public Feed | 交换经验证的 Raw、AI 和显式社区贡献 | ArXiv-data，Feed schema 2 |

Workspace schema 3；模板版本 6；Form Flow 0.0.8；PaperFlow Automation 1.5.1；
PDF++ 0.40.31。源码 main 基线为 20e493e（2026-09-21），本轮改进尚未提交。

## 已实现功能

### 论文收集与处理

| 功能 | 实现状态 | 验收范围 |
| --- | --- | --- |
| arXiv 主题发现、日期窗口、规则和 AI 相关性筛选 | 已实现 | 本机请求得到 100 候选，当前筛选通过 0；没有新增 AI 分析 |
| Obsidian Form Flow 手动添加论文 | 已实现 | 统一应用服务与自动测试通过；真实 UI 导入有历史验收 |
| CLI add/analyze/refresh/render/inspect | 已实现 | Golden Workflow 覆盖导入、分析、刷新、渲染和状态检查 |
| PDF 下载、版本、大小/header/SHA-256 验证 | 已实现 | 本机 37 个 PDF 索引无错误，版本化文件和哈希校验通过 |
| 去重、失败检查点、分析重试和本地 PDF/文本复用 | 已实现 | 自动测试通过；本机真实 AI 故障恢复场景待补验 |

### Obsidian 学习工作区

| 功能 | 实现状态 | 验收范围 |
| --- | --- | --- |
| 控制中心、论文库、阅读与复现队列、Bases | 已实现 | 本机控制中心加载，插件启用，Base 与 Workspace 校验通过 |
| Paper Hub、独立 AI 分析、独立 User Note | 已实现 | 37 篇论文/分析，用户文件保留有 Golden 覆盖 |
| 个人复盘、费曼答案与复现记录 | 已实现相关数据对象与入口 | 不覆盖已有用户文件有测试；本机完整学习使用场景未逐项验收 |
| 主题、方法、数据集实体和关系索引 | 已实现 | 实体迁移、导航与索引有测试；引文与语义相似关系分开记录 |
| caption-backed 图像提取、来源记录与图像导览 | 已实现 | 历史 29 篇样本/166 图像验收；本轮没有重新提取 |
| PDF++ 标注、Annotation Notes、Review | 已实现兼容模式 | 有历史真实高亮/评论验收与自动测试 |
| 每日简报、Inbox 调度、补跑 | 已实现 | 本机插件每日运行与 Inbox 均退出 0，当前共有 16 份日报 |

### Zotero 主阅读端

| 功能 | 实现状态 | 验收范围 |
| --- | --- | --- |
| 环境探测、活动 Profile 和 Local API 检测 | 已实现 | 只读检测，不直接访问 zotero.sqlite |
| loopback Core、会话认证与设备配对续期 | 已实现 | 本机 Core 启动/状态检查通过；本机 Zotero 设备配对待验收 |
| Collection、条目与 PDF 导入、身份和附件 mapping | 已实现 | 2026-07-28 隔离 Zotero 9.0.6 Profile 真实闭环通过 |
| 手动分析、条目事件排队、PDF 稳定性与分析复用 | 已实现 | 历史闭环和自动测试通过；本机主 Profile 待验收 |
| AI Markdown 子附件及完成后自动附加 | 已实现 | 历史 π0.5 样本验收通过，避免覆盖用户附件 |
| Reader 高亮/评论自动镜像与手动补同步 | 已实现 | 历史真实标注镜像通过；本机主 Profile 待验收 |
| 订阅 Inbox 和用户确认后导入 Zotero | 已实现 | 有 Core/插件测试；本机真实订阅到条目流程待验收 |

Zotero Reader 是新 Zotero 标注的编辑真源；Core 保存只读镜像。
新 Zotero 标注不会自动生成旧式 Obsidian Annotation Note，也不覆盖历史笔记。

### AI、公共数据和社区

| 功能 | 实现状态 | 验收范围 |
| --- | --- | --- |
| Codex/Claude/ChatGPT Web/Mock 配置与 profile | 已实现 | Codex CLI 更新至 0.162.1；GPT-6 Astra 已完成 π0.5 的本机真实重分析 |
| AI 分析版本、来源信息、哈希与重分析保护 | 已实现 | 本地已有 37 份完成分析；历史样本包含真实 Codex/Claude 来源 |
| ChatGPT 网页分析 | 已实现受控流程 | 历史安全交接通过；成功 PDF 上传/分析尚待验收 |
| Raw/AI Feed 构建、隐私扫描与发布 | 已实现 | 历史真实 GitHub 往返验收；本轮没有远程发布 |
| Raw/AI/Community 订阅与只读缓存 | 已实现 | 本机 37 Raw、37 AI、2 Community 验证通过，74 Raw/AI 全部复用，零冲突、零用户写入 |
| 私有标注/Review 显式选择公开、revision 和撤回 | 已实现 | 有 schema、隐私、哈希和篡改拒绝测试；历史两条贡献往返通过 |
| 社区 submit-pr 命令 | 目前仅本地计划 | 不应描述为自动创建并提交远程 PR |

## 本轮恢复与改进

1. 重建 Vault 专用 Python 3.12.14 环境，editable 安装 PaperFlow 1.5.1。
2. 更正迁移遗留 Vault 路径，恢复插件与本机 Obsidian CLI、Git 路径。
3. 更新 Automation 插件至 1.5.1，校正 Asia/Shanghai 时区及发布目标。
4. 修复 Doctor：标准 Windows 安装目录可自动发现，优先使用 Obsidian.com。
5. 修复 Workspace v3 PDF 链接误报：允许省略 .pdf、页码、别名，仍拒绝错误版本及相似文件名前缀。
6. 正式完成本机每日流程、Feed 同步与更新检查；插件状态均记录退出码 0。
7. 统一 CLI status 与插件 runtime 的调度状态，支持显式 --vault；补充自定义 Zotero PATH 检测。
8. 完成 π0.5 真实重分析，137 个已快照的 Raw/用户笔记/Review/Annotation 文件哈希均保持不变。
9. 确认 D:/Zotero 的 10.0.6 与已启用插件 1.5.1。开发原生 PaperFlow 设置页和工具菜单；用户确认首个预览包设置页可见，但按钮无响应。原因是误用不存在的 getPaneScope；第二个预览包改为本机真实 getScope，并逐一测试按钮处理器，原生点击/连接复验待完成。

自动发布保持关闭。更新检查确认 GitHub 当前稳定版本为 1.5.1，本机无需升级。
此前更新检查的 SSL 错误在本轮重试中没有复现，未声称所有网络故障永久消除。

## 当前质量证据

- 2026-10-12 完整 Python suite：393 passed、1 skipped。
- 全部九组 Node 集成测试通过，含设置页沙箱、空库工具菜单、配对、偏好兼容、北京时间作业分类与控制中心认证检查。
- Doctor 退出码 0；paths validate、workspace validate 和 Workspace v3 校验通过。
- 缺失 PDF、PDF 哈希错误、缺失笔记、PDF 笔记链接错误、Derived 路径错误、Base 错误均为 0。
- Git diff whitespace 检查通过；本轮未重新运行 Ruff、Mypy 或发布构建，不借用历史结果作为新代码的当前验证。
- 当前 status：37 篇论文、16 份日报、0 待处理 Inbox；有 1 个历史 failed job。
  status 的 SQLite 计数不能代表所有文件层标注或 Review 的总量。

## 尚未完成或存在限制

| 项目 | 当前缺口 |
| --- | --- |
| 本机新论文导入分析 | 已有论文的真实 AI 重分析已通过，新论文从 Zotero 导入到分析的闭环仍待验收 |
| 本机 Zotero 主 Profile 闭环 | 设置、配对、条目/PDF/AI Markdown 导入、Reader 高亮/评论镜像和 Core 重启自动续期均通过真实验收。PDF SHA-256 与分析输入一致；137 个受保护文件未改变。状态中的旧 failed 为 2026-07-28 历史记录 |
| GitHub 用户组权限产品 | 个人仓库 owner-only 提交器已实现，核对当前用户 threeyang3 对 ArXiv-data 有 admin/push 权限；组织 Team 和公开 fork 投稿尚未实现 |
| ChatGPT Web 成功分析 | 首次登录、模型选择、PDF 上传及成功结果待验收 |
| 无 Obsidian 的持续调度 | 已实现并启用 Core 独立每日/Inbox/订阅调度与 Windows 当前用户登录启动；原生任务直接启动的 Core 健康、owner=core。未做整机重新登录和异常退出测试 |
| 运行状态汇总 | CLI 的调度摘要已统一读取 plugin-state，包含来源与异常诊断；Zotero 原生状态需在配对后验收 |
| macOS/Linux 用户安装体验 | 有历史 CI，但不是已完成本机级验证的一键安装体验 |
| 本轮代码交付 | 修复在本地工作树生效，已制作设置预览包；未提交、推送或正式发布新版本 |

## 下一阶段建议

π0.5 的本机真实分析、Zotero 导入/附件、Reader 标注镜像和重启续期已完成验收。
第四个设置预览包新增作业列表、取消和按当前配置重试；原生新界面仍待安装验收。
Core 调度接管及无窗口登录任务已在本机启用，AI Markdown 现在展示既有完整分析章节。
费曼问题刷新保留答案与问题 ID，并允许添加个人问题。
个人社区仓库沿用 threeyang3/ArXiv-data，程序源码仓库为 threeyang3/PaperRead。
显式哈希确认的 owner-only 草稿 PR 提交器已实现，保留不可变 revision，维护
manifest/checksum。现有两份 outbox 快照与远端完全一致，本轮没有远端写入。
真实新增内容草稿 PR 的本机验收仍待用户选择新内容并明确提交授权；CLI 认证
从 GH_TOKEN/GITHUB_TOKEN 环境读取，不会借用 Codex 连接的凭据。
后续重点为正式发布交付和组织/公开投稿权限扩展。用户笔记/复盘的自动回归保护已通过；
不将其等同于用户实际完成了个人学习与复盘。

## 证据入口

- [验证矩阵](../verification-matrix.md)
- [架构与数据层](../architecture.md)
- [个人学习流程](../learning-workflow.md)
- [数据权限](../artifact-permissions.md)
- [Zotero 集成](../../integrations/zotero-paperflow/README.md)
- [社区贡献](../community-contributions.md)

本机恢复和本轮操作记录分别位于 Vault 的
`.paperflow/backups/local-restore-20261011-162249/` 和
`.paperflow/backups/improvements-20261012/`。
