# Windows 安装

- Applies to PaperFlow 1.5.x
- Workspace schema: 3
- Feed schema: 2

PaperFlow 的 Windows 发布物是
`PaperFlow-Offline-Installer-<version>.zip`。它包含 wheel、安装/卸载脚本、
模板和集成资源，但不包含 Python 运行时，因此不是免安装、完全自包含的
Portable 程序。安装前需要 Python 3.11+，并建议使用 `pipx` 或 `uv`。

## 普通用户安装

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

## 回滚与卸载

卸载应用：

```powershell
.\uninstall.ps1 -Method pipx
# 也可选择 uv 或 pip
```

卸载脚本只卸载 PaperFlow Python 包，不删除 Vault。Workspace 回滚恢复正式
备份覆盖范围内的文件，不会删除备份后新增的用户文件；迁移产生的可重建
Derived 文件可能保留，可随后用 health/cleanup 流程处理。
