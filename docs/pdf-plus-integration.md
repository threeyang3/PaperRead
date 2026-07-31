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

## 可视化标注适配

Automation 插件的“从当前 PDF / 选区创建标注”按以下顺序运行：

1. feature-detect `pdf-plus:copy-link-to-selection` 与剪贴板读取能力；
2. 调用命令并校验复制结果确实是当前版本 PDF 的
   `#page=N&selection=a,b,c,d` 链接；
3. 打开已预填的 PaperFlow 表单；
4. 通过 `paperflow annotation create --apply` 写入私有 User 数据并刷新索引。

Obsidian 的命令管理器不是稳定公共 API，因此调用只存在于可失败的适配层，
任何异常都会退化为表单。用户可粘贴 PDF++ 链接，或填写页码和实际所见文本；
PaperFlow 不会把文本伪造成 `selection=` 坐标。未安装 PDF++ 时生成原生
`[[file.pdf#page=N]]`，点击仍可返回正确版本和页码。PaperFlow 不修改
`enablePDFEdit`，也不启用 `autoCopy` / `autoPaste`。

PDF++ 链接的四元组选区坐标与 PaperFlow `TextQuoteSelector` 分开保存。版本更新
后旧链接仍指向旧 PDF；重定位继续使用 Annotation revision/reanchor 流程。
从 Obsidian DOM 或剪贴板取得的链接可能把查询参数分隔符编码为 `&amp;`；
Automation 和 Python anchor parser 都会先进行 HTML 反转义，再校验 `page`、
`selection` 与 `color`，不会把转义文本写入正式 anchor。

阅读工作区打开前会执行
`paperflow annotation ensure-index <paper_uid> --apply`。CLI 返回 Workspace
配置所决定的规范索引路径，因此自定义标注根目录和旧版年份目录都不会使插件
打开一个空的平行索引。
