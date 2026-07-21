# PaperFlow 1.5 用户与维护者指南

PaperFlow 1.5 把“阅读 PDF、写个人标注、形成个人评审、查看社区观点、选择性
公开贡献”做成相互独立的能力。个人内容默认私有，社区内容只读，公开发布必须
显式选择和再次确认。

## 用户最短路径

1. 在 Obsidian 打开一篇 PaperFlow 论文笔记。
2. 命令面板运行“PaperFlow: 打开论文阅读工作区”。
3. 左侧阅读 PDF；从命令面板、Ribbon、文件菜单或控制中心选择“创建 PDF
   标注”。推荐安装官方 PDF++；未安装仍可用 Obsidian 原生页码链接。
4. 在控制中心的并列入口中查看“阅读、标注、评审、社区、发布贡献”。
5. 运行 `paperflow annotation sync --dry-run` 检查标注协议。

PDF++ 可用时，插件会尝试复制当前真实选区并预填表单。该命令或剪贴板不可用
时会明确显示降级表单，由用户填写页码、所见文本和评论；不会伪造选区。保存
通过中央 CLI 写入 User 层并刷新索引，Nutstore 双修改冲突仍会拒绝覆盖。

PDF 按 arXiv 版本保存为 vN，旧版本不覆盖。个人评分、AI 分数和社区评分分别
显示。英文论文标题、摘要、引用、图注和正文不因中文界面被翻译。

## 隐私

- 标注和 Review 位于 User 层，默认永不发布。
- 订阅社区记录位于只读 cache，不能覆盖个人内容。
- 只有显式 select 才生成公共快照；引用最多 500 字符。
- 路径、邮箱、凭据、HTML/脚本、图片、PDF、全文和用户字段会被阻止。
- 真实 GitHub PR 不自动执行。

## 升级

先运行 `paperflow migrate workspace-v3 --dry-run`。应用迁移会完整备份
`.obsidian` 和 Vault 数据，复制而不是删除旧 PDF；更新记录后会通过中央
compose/render 路径重渲染已有论文笔记，并验证新 PDF 链接，同时保留个人字段、
标签和用户笔记。回滚命令 `paperflow migrate rollback-workspace-v3` 默认也是
dry-run，只恢复正式备份中的校验文件，不删除之后创建的用户文件。详见
[1.5 迁移指南](1.5-migration-guide.md)。

## 维护者

应用版本单一来源为 `_version.py`。新增稳定 YAML 字段仍必须同步更新 Schema、
模板、迁移、测试和文档；本轮新增内容使用独立 Annotation/Community Schema，
没有污染论文平铺 YAML。

公共数据仍由 ArXiv-data 承载；Raw/AI v1 路径在 Feed v2 保持兼容。社区发布
默认关闭，贡献按论文拆分 manifest；订阅端必须重新计算 canonical
`content_sha256`，拒绝被篡改的 revision。维护者必须完成完整 pytest、Node 生命周期、
Doctor、audit、迁移、Base、Obsidian runtime、发布物白名单和干净 clone 验证。

截至 2026-07-21，PaperRead 1.5.0 的源代码、113 项 pytest、2 项 Node 测试、
模拟 Workspace v3 迁移/回滚、Community 篡改拒绝和本地发布物验证已完成。
真实 `ArxivLearn` Vault 已复制并渲染 32/32 篇，但旧 1.5.0 代码未更新
Derived PDF 路径，验证因此拒绝全部 32 篇。安装修复 wheel 后应直接重跑
`workspace-v3 --apply` 进入 repair mode，再执行 verify、Doctor、audit 与
Obsidian 交互验收；无需手改论文。
