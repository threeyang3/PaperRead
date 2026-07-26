[CmdletBinding()]
param(
  [string]$ProfilePath = "",
  [switch]$Reset,
  [switch]$Launch,
  [int]$WaitSeconds = 300
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot ".."))
$rootPath = $root.Path.TrimEnd("\\")
$profile = if ($ProfilePath) {
  [IO.Path]::GetFullPath($ProfilePath)
} else {
  Join-Path $rootPath "var/zotero-manual-e2e-profile"
}
$varRoot = Join-Path $rootPath "var"

if (-not $profile.StartsWith($varRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
  throw "ProfilePath 必须位于 PaperRead\var 下；脚本不会触碰主 Zotero Profile。"
}

$zotero = @(
  (Join-Path ${env:PROGRAMFILES} "Zotero/zotero.exe"),
  (Join-Path ${env:LOCALAPPDATA} "Programs/Zotero/zotero.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $zotero) { throw "未找到 Zotero zotero.exe。" }

$xpi = Get-ChildItem (Join-Path $rootPath "dist/PaperFlow-Zotero-*.xpi") -File |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $xpi) {
  throw "未找到 XPI。请先运行 python scripts/build_release.py。"
}

if ($Reset -and (Test-Path -LiteralPath $profile)) {
  Remove-Item -LiteralPath $profile -Recurse -Force
}
New-Item -ItemType Directory -Force -Path (Join-Path $profile "extensions") | Out-Null
$dataDir = Join-Path $profile "zotero-data"
# Zotero validates the configured data directory during first startup.
# Create it before launching the disposable profile so Zotero never offers
# to substitute the user's real/default data directory.
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
$dataDirEscaped = $dataDir.Replace("\", "\\")

# These preferences only affect this disposable test profile.
@"
user_pref("extensions.autoDisableScopes", 0);
user_pref("extensions.enabledScopes", 5);
user_pref("app.update.disabledForTesting", true);
user_pref("extensions.update.enabled", false);
user_pref("extensions.getAddons.discovery.api_url", "data:, ");
user_pref("extensions.zotero.dataDir", "$dataDirEscaped");
user_pref("extensions.zotero.useDataDir", true);
user_pref("extensions.zotero.firstRun.skipFirefoxProfileAccessCheck", true);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("browser.sessionstore.resume_from_crash", false);
"@ | Set-Content -LiteralPath (Join-Path $profile "user.js") -Encoding UTF8

$id = "paperflow-zotero@threeyang"
$statePath = Join-Path $profile "extensions.json"

Write-Host "隔离 Profile: $profile"
Write-Host "XPI: $($xpi.FullName)"
Write-Host ""
Write-Host "请在隔离 Zotero 中完成一次人工安装："
Write-Host "  工具 -> 插件 -> 齿轮 -> 从文件安装插件"
Write-Host "  选择上面的 XPI，确认安装并重启 Zotero。"

if (-not $Launch) {
  Write-Host "未启动 Zotero。重新运行本脚本并添加 -Launch 才会启动隔离实例。"
  exit 0
}

$process = Start-Process -FilePath $zotero -ArgumentList @(
  "--new-instance", "--profile", $profile
) -PassThru
Write-Host "已启动隔离 Zotero (PID $($process.Id))。"

$deadline = [DateTime]::UtcNow.AddSeconds([Math]::Max(5, $WaitSeconds))
do {
  Start-Sleep -Seconds 2
  if (Test-Path -LiteralPath $statePath) {
    try {
      $state = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
      $addon = @($state.addons) | Where-Object { $_.id -eq $id } | Select-Object -First 1
      if ($addon) {
        $active = [bool]$addon.active
        $disabled = [bool]$addon.userDisabled -or [bool]$addon.appDisabled
        if ($active -and -not $disabled) {
          Write-Host "PaperFlow Zotero 插件已启用。"
          exit 0
        }
        Write-Host "已发现插件，但仍未启用 (active=$active, userDisabled=$($addon.userDisabled), appDisabled=$($addon.appDisabled))。"
      }
    } catch {
      # Zotero may write extensions.json while it is still starting.
    }
  }
} while ([DateTime]::UtcNow -lt $deadline)

Write-Error "等待超时。请确认已在插件窗口选择 XPI 并重启隔离 Zotero；没有修改主 Profile。"
exit 1
