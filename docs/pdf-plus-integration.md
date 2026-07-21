# PDF++ 集成

推荐使用官方 Obsidian 社区插件 `pdf-plus`。PaperFlow 测试范围为
`>=0.40.7,<1.0.0`，推荐 0.40.31；最低 Obsidian 1.5.8。

```powershell
paperflow integration pdf-plus status
paperflow integration pdf-plus install --dry-run
paperflow integration pdf-plus configure --dry-run
paperflow integration pdf-plus repair --dry-run
paperflow integration pdf-plus upgrade
```

`install` 只调用 Obsidian 官方社区插件安装入口，不下载或复制插件代码。
`configure` 合并缺失设置，不覆盖用户值；冲突写入 `data.json.new`。修改
`.obsidian` 前会建立集成备份。

推荐配置关闭 PDF 直接编辑。若用户自行启用，编辑后的文件是 User-derived
PDF，不再是 Raw，也不会发布到 Feed。PaperFlow 只解析公开的 Obsidian 链接
语法，不调用 PDF++ 私有 JavaScript API；插件缺失时保留 page-only 原生链接。
