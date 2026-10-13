# Windows 安装

- Applies to PaperFlow 1.5.x
- Workspace schema: 3
- Feed schema: 2

PaperFlow 的 Windows 发布物是
`PaperFlow-Offline-Installer-<version>.zip`。它包含 wheel、安装/卸载脚本、
模板和集成资源，但不包含 Python 运行时，因此不是免安装、完全自包含的
Portable 程序。安装前需要 Python 3.11+，并建议使用 `pipx` 或 `uv`。

## 普通用户安装

### Obsidian 首次向导（本地预览功能）

安装新版 PaperFlow Obsidian 插件后，未初始化的资料库会自动打开首次向导。
已有资料库可通过命令面板“PaperFlow：首次设置 / 初始化资料库”或插件设置
中的“打开向导”进入。向导只针对当前打开的本地资料库。

1. 选择安装了支持向导功能的 PaperFlow Core 的 Python 可执行文件，点击“检测并预览”。
2. 确认目录、配置、模板、Bases 与入门页；点击“初始化当前资料库”。已有同名目标
   文件会阻止初始化，配置在写入前备份。已有 Workspace 会直接进入连接阶段。
3. 启动或检查 Core，复制令牌，在 Zotero 设置 → PaperFlow 中配对。
4. 安装并启用 Form Flow 后，点击“准备手动录入表单”；随后打开控制中心配置 AI，
   手动导入第一篇论文。新资料库暂不启用自动调度，也不调用 AI 或发布远端内容。

两个插件不包含 Python/Core/AI 运行环境；缺少 Core 时向导提供安装指引。
旧版 Core 即使版本号相同，也可能缺少 `workspace onboard`，需要使用支持该功能的新版构建。
本功能已在本机代码中实现，尚未发布为正式 GitHub/PyPI 版本。

本地配套预览包为 `dist/PaperFlow-First-Run-Preview-20261013.zip`，包含匹配的
Core wheel、Obsidian 插件、Zotero 设置预览插件、安装说明及校验和。
建议用独立 Python 环境安装 Core wheel，再在向导中选择该环境的 Python。
复用同版本号旧环境时需明确 `--force-reinstall`；新 wheel 不代表运行中的旧 Core
已更新，应先停止旧进程再升级。插件不包含 Python 和第三方依赖。

初始化先暂存并验证所有生成文件，再发布 Workspace 配置；遇到可捕获的写入异常
会清理未被用户修改的生成内容。断电或强制终止不保证自动回滚，残留冲突需要先
保留现场并核对备份。重复准备 Form Flow 时，自定义表单持续进入合并复核，
不会因旧状态记录而自动覆盖。

调试或脚本集成可使用只读命令 `paperflow workspace onboard --vault <path>`；
执行初始化需加 `--apply --confirm-digest <预览摘要>`。不要对已有库使用强制初始化。

联网环境优先使用隔离工具：

```powershell
pipx install paperflow
# 或
uv tool install paperflow
```

随后验证：

```powershell
paperflow --version
paperflow --help
paperflow init --non-interactive --vault "E:\My PaperFlow Vault"
paperflow workspace info --vault "E:\My PaperFlow Vault"
```

## GitHub Release 离线安装

1. 解压 `PaperFlow-Offline-Installer-<version>.zip`，不要只打开 ZIP 内文件。
2. 在解压目录运行以下一种命令：

```powershell
.\install.ps1 -Method pipx
.\install.ps1 -Method uv
.\install.ps1 -Method pip
```

脚本会定位包内 wheel、检查所选工具、验证安装退出码，并实际执行
`paperflow --version` 与 `paperflow --help`。`pipx`/`uv` 本身及 Python
依赖仍须事先可用；离线机器应预先安装这些运行工具。

## 源码开发安装

```powershell
git clone https://github.com/threeyang3/PaperRead
cd PaperRead
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,quality]"
```

开发环境不是最终用户安装，也不要把项目仓库当作 Obsidian Vault。

## 升级已有 Workspace

先升级应用，再对目标 Vault 运行：

```powershell
paperflow --version
paperflow update workspace --vault "E:\My PaperFlow Vault"
paperflow doctor --vault "E:\My PaperFlow Vault"
```

迁移前会建立正式备份；不得手工批量改写 Raw、AI 或生成的论文记录。

## 可选：关闭 Obsidian 后继续调度

从当前 Vault 的虚拟环境执行，避免使用另一套 Python 注册启动路径：

```powershell
& "E:\Develop\ArxivLearn\.paperflow\.venv\Scripts\python.exe" -m paperflow.cli config set obsidian.scheduler_owner core --vault "E:\Develop\ArxivLearn"
& "E:\Develop\ArxivLearn\.paperflow\.venv\Scripts\python.exe" -m paperflow.cli zotero service autostart --apply --vault "E:\Develop\ArxivLearn"
```

该步骤注册当前用户的无窗口登录任务；以用户登录状态和已有 AI 登录凭据运行，
不注册 SYSTEM 服务。它直接监督 Core 进程，异常退出重试三次。注册不会立即
停止已有 Core；需要重启 Core 以加载新代码，或在下一次登录生效。
移机、移动 Vault 或更换虚拟环境后重新注册；旧路径的任务应先 `--remove`。
正式升级仍需先备份、校验发布物校验和，再升级应用和 Workspace。

撤销这一项只需：

```powershell
paperflow zotero service autostart --remove --vault "E:\Develop\ArxivLearn"
paperflow config set obsidian.scheduler_owner obsidian --vault "E:\Develop\ArxivLearn"
```

撤销登录任务不删除论文或用户数据，也不停止已经运行的 Core。
若回滚到尚不认识 `scheduler_owner` 的旧应用，先用新应用运行
`paperflow config unset obsidian.scheduler_owner --vault <vault>`，再降级；
这样旧配置模型不会因为新选项而拒绝启动。

## 回滚与卸载

卸载应用：

```powershell
.\uninstall.ps1 -Method pipx
# 也可选择 uv 或 pip
```

卸载脚本只卸载 PaperFlow Python 包，不删除 Vault。Workspace 回滚恢复正式
备份覆盖范围内的文件，不会删除备份后新增的用户文件；迁移产生的可重建
Derived 文件可能保留，可随后用 health/cleanup 流程处理。
