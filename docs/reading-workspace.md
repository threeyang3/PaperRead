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

标注建议使用 PDF++ 复制链接，再用 PaperFlow 同步/校验命令固化 selector 和
PDF hash。历史 PDF 仍可打开；切换版本不会自动重定位标注。
