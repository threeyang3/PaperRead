# Obsidian 阅读工作区

先打开一篇 PaperFlow 论文笔记，再执行命令面板：

```text
PaperFlow: Open paper reading workspace
```

插件打开：

- 左侧：当前版本 PDF；
- 右上：该论文标注索引；
- 右下：个人 Review；
- 右侧附加页：只读 Community Note。

插件为四个目标使用四个独立 leaf。Review 明确以 PDF leaf 为锚点创建水平分栏，
不会因当前 active leaf 改变而丢失；标注与 Community 使用不同的右侧 leaf。
全部文件打开后，插件等待 PDF leaf 完成 reveal，并把焦点切回 PDF。

缺少标注、Review 或 Community Note 时，插件只创建私有/派生骨架，不创建公共
贡献。控制中心提供“阅读、标注、评审、社区、发布贡献”五个并列入口；它们与
抓取、分析和 Agent 设置没有前后继关系。

Ribbon、命令面板、PDF/论文文件菜单和控制中心都提供“创建 PDF 标注”。安装
PDF++ 时，一键入口优先运行其 Copy link to selection 命令并预填表单；否则
明确退化到页码、所选文本和评论表单。高亮、评论、问题和批评均由 PaperFlow
CLI 中央写入 User 层，并立即刷新 `60 Annotations` 索引；不会直接修改 PDF。

标注链接固化 selector、PDF 版本和 SHA-256。历史 PDF 仍可打开；切换版本不会
静默改写标注，需通过 revision/reanchor 流程定位新版本。
