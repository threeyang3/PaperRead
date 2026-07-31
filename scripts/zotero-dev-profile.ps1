[CmdletBinding()]
param(
  [string]$ProfilePath = "",
  [switch]$Reset,
  [switch]$Launch,
  [int]$WaitSeconds = 30
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path.TrimEnd("\")
$varRoot = [IO.Path]::GetFullPath((Join-Path $root "var")).TrimEnd("\")
$profile = if ($ProfilePath) { [IO.Path]::GetFullPath($ProfilePath) } else { Join-Path $varRoot "zotero-dev-profile" }

if (-not $profile.StartsWith($varRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
  throw "ProfilePath 必须位于 PaperRead\var 下；脚本不会触碰主 Zotero Profile。"
}

$source = [IO.Path]::GetFullPath((Join-Path $root "integrations\zotero-paperflow"))
if (-not (Test-Path -LiteralPath (Join-Path $source "manifest.json"))) {
  throw "未找到 PaperFlow Zotero 源码 manifest.json。"
}
$zotero = @(
  (Join-Path ${env:PROGRAMFILES} "Zotero\zotero.exe"),
  (Join-Path ${env:LOCALAPPDATA} "Programs\Zotero\zotero.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $zotero) { throw "未找到 Zotero zotero.exe。" }

if ($Reset -and (Test-Path -LiteralPath $profile)) {
  Remove-Item -LiteralPath $profile -Recurse -Force
}
New-Item -ItemType Directory -Force -Path (Join-Path $profile "extensions") | Out-Null
$dataDir = Join-Path $profile "zotero-data"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

# Zotero's documented proxy workflow asks developers to remove these cached
# build markers before restarting so the extension database is rescanned.
# Only the disposable profile is touched.
$prefsPath = Join-Path $profile "prefs.js"
if (Test-Path -LiteralPath $prefsPath) {
  $prefs = Get-Content -LiteralPath $prefsPath -ErrorAction Stop
  $prefs | Where-Object { $_ -notmatch 'extensions\.lastApp(BuildId|Version)' } |
    Set-Content -LiteralPath $prefsPath -Encoding UTF8
}

# Zotero's official development workflow: a file named after the add-on ID
# points to the unpacked source directory. This avoids production XPI signing
# requirements and is confined to PaperRead/var.
$extensionProxy = Join-Path $profile "extensions\paperflow-zotero@threeyang"
Set-Content -LiteralPath $extensionProxy -Value $source -NoNewline -Encoding UTF8

$escapedData = $dataDir.Replace("\", "\\")
@(
  'user_pref("extensions.autoDisableScopes", 0);',
  'user_pref("extensions.enabledScopes", 5);',
  'user_pref("app.update.disabledForTesting", true);',
  'user_pref("extensions.update.enabled", false);',
  ('user_pref("extensions.zotero.dataDir", "' + $escapedData + '");'),
  'user_pref("extensions.zotero.useDataDir", true);',
  'user_pref("extensions.zotero.firstRun.skipFirefoxProfileAccessCheck", true);',
  'user_pref("browser.shell.checkDefaultBrowser", false);',
  'user_pref("browser.startup.homepage_override.mstone", "ignore");',
  'user_pref("browser.sessionstore.resume_from_crash", false);'
) | Set-Content -LiteralPath (Join-Path $profile "user.js") -Encoding UTF8

Write-Host "隔离 Profile: $profile"
Write-Host "Extension Proxy: $extensionProxy -> $source"
Write-Host "这是开发加载方式，不是生产 XPI 安装；不会修改主 Profile 或 D:\Zotero。"
if (-not $Launch) {
  Write-Host "未启动 Zotero。添加 -Launch 以启动一次隔离实例。"
  exit 0
}
$process = Start-Process -FilePath $zotero -ArgumentList @('--new-instance', '--profile', $profile) -PassThru
Write-Host "已启动隔离 Zotero (PID $($process.Id))。请在工具 -> 插件中确认 PaperFlow 已加载。"
Start-Sleep -Seconds ([Math]::Max(2, [Math]::Min($WaitSeconds, 30)))
