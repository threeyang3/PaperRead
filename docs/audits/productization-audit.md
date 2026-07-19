# PaperFlow 产品化现状审计

> 本文是 2026-07-17 的历史审计快照，不是当前安装或运维说明。当前状态请以
> [用户与维护者指南](../维护者与用户指南.md)和
> [验证矩阵](../verification-matrix.md)为准。
>
> 审计时间：2026-07-17 15:13（Asia/Shanghai）  
> 审计对象：`E:/ObsidianVaults/ArxivLearn`  
> 基线备份：`.paperflow/backups/productization-20260717-151342`

## 1. 审计结论

当前系统是一个功能完整度较高、但程序与个人 Vault 强耦合的单用户工作流，尚不能作为通用 PaperFlow 产品发布。采集、PDF、AI、SQLite、Markdown、Bases、Form Flow、Obsidian 内部调度和测试均已存在；主要缺口是可移植 Workspace、正式版本契约、可回滚迁移、四层数据、公共 Feed、标准安装包、跨平台路径、产品化 CLI、CI/CD 和陌生用户文档。

当前数据量很小但是真实数据，适合在严格备份和 dry-run 之后执行可验证迁移：

| 项目 | 基线 |
|---|---:|
| 论文笔记 | 2 |
| 旧混合 JSON | 2 |
| PDF | 2 |
| 每日简报 | 2 |
| Inbox/已处理/失败请求文件 | 3 |
| User sidecar | 0 |
| pytest | 102 passed |

## 2. 当前代码与仓库状态

- 根目录包含 `.git`，但它不是有效 Git 仓库；`git rev-parse` 和 `git status` 均失败。不能依赖分支回退，因此本轮使用文件级备份、哈希清单和迁移日志。
- Python 包位于 `.paperflow/src/paperflow`，测试位于 `.paperflow/tests`。
- `pyproject.toml` 已使用 Hatchling，并声明 `paperflow = "paperflow.cli:app"`，但 wheel 指向 `.paperflow/src/paperflow`，源码与用户 Workspace 混合。
- 顶层尚无标准 `src/`、`schemas/`、`templates/`、`integrations/`、`migrations/`、`tests/`、`examples/`、`docs/`、`scripts/` 或 `.github/workflows/` 产品目录。
- 没有 GitHub Actions、Dependabot、发布工作流、CHANGELOG、贡献指南、安全政策或许可证决策阻断文件。
- 当前应用版本为 `0.1.0`；没有独立的 Workspace、Raw、AI、User、Feed、模板和 Form Flow 集成版本体系。

## 3. 当前功能与数据流

```text
arXiv/DOI/URL/Form Flow
  → 元数据解析与去重
  → PDF 下载、哈希与文本提取
  → Codex/Claude/Mock 分析
  → 单个混合 JSON
  → SQLite 索引
  → Markdown + YAML
  → Bases/Dashboard/简报
```

已实现：

- arXiv 每日增量发现、规则筛选与轻量 AI 筛选。
- PDF 下载、文件头/大小/哈希检查和 PyMuPDF/pdftotext 提取。
- Codex、Claude、Mock adapter 和严格分析 JSON Schema。
- SQLite 作业、论文、分析、请求、失败记录。
- 原子文件写入、流水线锁、失败重试。
- 用户字段与 `USER_NOTES_START/END` 保护。
- Form Flow 0.0.8 安全请求。
- Obsidian Bases、Dashboard、中文 i18n 和本地 PaperFlow Automation 插件。
- 当前两个 Windows Task Scheduler 任务已不存在；自动化由 Obsidian 打开状态驱动。

## 4. 当前硬编码

阻断通用安装的硬编码包括：

- `config.py` 的 `FIXED_VAULT = E:/ObsidianVaults/ArxivLearn`，并拒绝其他 Vault。
- `doctor.py`、`acceptance.py` 对当前 Vault、特定论文和固定目录的断言。
- PowerShell setup/scheduler 脚本中的绝对 Vault 路径。
- Bases filter 固定 `10 Papers`。
- validation、迁移和若干业务逻辑直接拼接 `10 Papers`、`00 Dashboard`、`.paperflow/data/papers`。
- `paperflow.yaml` 保存当前用户绝对路径、模型和个人研究 profile，不适合作为公开默认配置。

## 5. 当前数据模型与风险

每个旧 JSON 有约 76 个顶层字段，同时混合：

- 24 个 `paper_*` 来源字段；
- 31 个 `ai_*` 分析字段；
- 9 个 `user_*` 本地用户字段；
- 7 个 `system_*` 运行字段；
- `sections`、`extraction` 和本地 `note_path/json_path`。

两个 JSON 均没有独立数据 Schema 版本，只记录 `system_pipeline_version=0.1.0`。风险：

1. 不能安全公开导出，容易泄露用户字段和本地路径。
2. AI 重新分析可能覆盖旧分析，没有稳定 `analysis_id` 和不可变记录。
3. Raw 新版本没有统一不可变快照契约。
4. User Data 只有 Markdown/YAML 投影，没有 sidecar。
5. 未知字段没有正式 `extensions` 契约。
6. 当前 `migrate_v2` 是业务函数，不具备统一 plan/apply/verify/rollback/history、全局锁、staging 和失败恢复。
7. 路径由业务函数拼接，没有受限模板解释器、冲突预览或 redirect。
8. 当前 Codex 隔离逻辑复制用户 `auth.json` 到临时目录，与新产品“不得读取或复制凭证”要求冲突，必须移除。

## 6. SQLite、Schema、模板和 Obsidian

- SQLite 表：`papers`、`paper_versions`、`discovery_runs`、`import_jobs`、`analysis_runs`、`manual_requests`、`failed_jobs`、`schema_migrations`。
- 数据库迁移表只存整数版本和时间，没有 migration ID、计划、哈希、备份、验证、回滚或结果详情。
- JSON Schema 目前只有论文分析与轻量相关性分析。
- Markdown 模板直接存放在 Vault 的 `90 System/Templates`，不是版本化程序资源。
- 五个 Bases 和 Dashboard 可用，但 Base 根目录及 paper source folder 未完全配置化。
- Form Flow 资源只存放在当前 Vault，缺少版本化集成 bundle 和冲突安全升级机制。

## 7. AI Provider 审计

- 已有 `AIAdapter` Protocol 和 Codex/Claude/Mock factory，但接口只有 `analyze`，缺少 availability、model listing、config validation 和 provenance。
- 业务配置只有单组 analysis/relevance provider，尚无 triage/full/fallback/reanalysis profile。
- 模型空值当前被转换为字符串 `configured-default`，没有明确保留 CLI 默认语义。
- 没有 CLI capability 探测、参数 allowlist、禁止危险参数或稳定 analysis identity。
- 已有真实 Codex 分析可以且必须复用；产品化迁移不应重新下载 PDF、提取文本或调用付费模型。

## 8. 需要保留的兼容行为

- 根命令 `paperflow add/analyze/render/refresh/rebuild-index/rebuild-bases` 至少跨一个次版本继续可用，并转发到新的命令组。
- 当前 `paperflow.ps1` 和 `paperflow.cmd` 继续作为 Workspace shim。
- 当前论文笔记、PDF、Bases、Dashboard、Form Flow 和 Obsidian 自动化继续可用。
- `user_*`、用户标签和用户笔记区不被覆盖。
- 现有两个 JSON、两份 PDF、两篇笔记、请求历史和简报均保留可追溯原始快照。
- 现有 Codex 分析按内容哈希、provider、model、prompt、Schema 和 profile 生成 identity 后复用。

## 9. 拟迁移结构

采用“根目录为产品源码工作树、当前 Vault 为兼容 Workspace”的原地重构，不创建嵌套 Git 仓库：

```text
src/paperflow/                 可发布 Python 包
schemas/                      版本化数据与 Feed Schema
templates/                    版本化默认模板
integrations/                 Form Flow/Obsidian 资源
migrations/                   正式迁移定义
tests/                        产品测试
examples/                     脱敏配置和 sample Vault
docs/                         陌生用户文档和审计报告
scripts/                      安装、构建和 portable
.github/                      CI、build、release、feed validation

当前 Vault/.paperflow/
  workspace.yaml
  workspace.local.yaml
  state/
  data/raw/
  data/ai/
  data/user/
  data/derived/
  migrations/
  backups/
```

构建系统只包含显式程序资源，不包含当前论文、PDF、日志、SQLite、个人笔记或 Workspace local 配置。

## 10. 实际实施结果

截至 2026-07-17 17:10（Asia/Shanghai）：

- 标准应用包已迁移到 `src/paperflow`，应用版本为 `1.1.0`；Workspace、Raw、AI、User、Feed、模板和 Form Flow 具有独立版本。
- `paperflow init --vault` 支持任意 Vault；严格 Pydantic 配置按 defaults → workspace → local → env → CLI 分层。
- 正式 migration engine 已具备 status/plan/apply/verify/rollback/history、全局锁、SHA-256、备份、staging、原子替换、失败恢复和未知字段 `extensions`。
- 当前 Workspace 的初始 run 已通过正式 rollback 验证可逆性，并以最终 Schema 重新执行 `workspace-0001-productization-20260717-172616-b8ef5d00`：2 Raw、1 AI、2 User、2 Derived；旧 JSON、笔记与 PDF 原样保留。
- 即时迁移前备份为 `.paperflow/backups/workspace-20260717-165825`；最终迁移自动快照为 `.paperflow/backups/workspace-0001-productization-20260717-172616-b8ef5d00`。
- 两篇笔记和两个 PDF 的迁移后 SHA-256 与迁移前清单一致；路径 dry-run 为 0 move、0 redirect、0 conflict。
- Codex runtime 不再打开或复制 `auth.json`；Provider 统一支持 capability、模型/profile、参数 allowlist、provenance 和稳定 analysis identity。
- 公共 Feed 支持确定性 build/validate/scan/diff、link-only PDF、校验和、信任模式、不可执行远程内容和保留多来源分析。
- Form Flow 0.0.8 集成已登记为 version 1；三个资源哈希一致，无用户冲突。Bases 由配置根生成，Markdown 模板版本为 2。
- Obsidian Automation 已升级为 1.1.1，使用标准 `src` 或已安装应用，不依赖 Windows Task Scheduler；在布局就绪后监听 Form Flow 请求文件事件并防抖触发 Inbox，启动和五分钟轮询作为兜底。Obsidian Control Center 默认随工作区加载自动打开（设置中可关闭），覆盖论文导入、AI profile 原子配置、GitHub Feed 订阅/同步、发布预检、独立 Feed Git 初始化/状态/提交和二次确认 push。所有操作使用固定 allowlist、`shell: false`，Git hooks 被禁用。
- 本机运行的 Obsidian 应用包为 1.12.7，但安装器壳仍为 1.9.12，未达到官方 CLI 要求的 1.12.7 installer；因此 `plugin:reload/restart` 不能作为可靠热重载方式。1.1.1 文件、样式、启用状态和 integration 3 哈希状态已就位，并通过 Node DOM/生命周期测试；需要从系统托盘完全退出 Obsidian 后重新打开，当前进程才会加载自动打开行为。
- 本地构建已生成 wheel、sdist、Windows portable、Schema/模板包、迁移说明和 `SHA256SUMS`；独立 wheel 安装和 CLI 启动成功。
- 5 个 GitHub Actions 工作流和 Dependabot 已创建；未创建远程仓库、未 push、未上传 PyPI、未创建 Release。
- 用户授权后，PaperFlow 程序代码选择 MIT License，当时与程序同仓的首批
  数据选择 CC BY 4.0；发布者为 `threeyang`。该历史 Feed 经
  build/validate/scan 后首次推送至 `threeyang3/PaperRead`。其后公共数据已
  完整迁移到独立的 `threeyang3/ArXiv-data` 仓库。
- PaperFlow 1.1.0 回归为 155 passed，另有 2 个 Node 调度器/控制中心生命周期集成测试通过；Doctor、产品 audit、迁移 verify、路径 validate、SQLite、链接和 Obsidian 内部调度均通过。
