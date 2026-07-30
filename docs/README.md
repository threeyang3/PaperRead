# PaperFlow 文档导航

这里是 PaperFlow 文档的唯一入口。当前功能以主指南、专题文档和验证矩阵为准；
`archive/` 只保存旧版本与阶段性审计，不应据此判断当前能力。

## 第一次使用：按这个顺序

1. [快速开始](getting-started.md)：安装、初始化和第一篇论文。
2. [用户与维护者指南](维护者与用户指南.md#用户指南)：理解数据边界，并选择
   Zotero 或 Obsidian 作为主要入口。
3. 选择阅读前端：
   - [Zotero 9+ 集成](../integrations/zotero-paperflow/README.md)：Collection、
     PDF、Core 配对、AI Markdown 和 Reader 标注镜像。
   - [Obsidian 集成](obsidian-integration.md)：控制中心、Form Flow、Bases 和
     Automation。
4. 遇到问题先看[故障排查](troubleshooting.md)，不要直接修改生成数据或数据库。
5. 需要确认“现在到底验证了什么”时，看[验证矩阵](verification-matrix.md)。

## 用户文档

### 论文工作区与阅读

- [Paper Workspace](paper-workspace-artifacts.md)：Paper Hub、AI 分析和用户笔记。
- [阅读工作区](reading-workspace.md)：Obsidian PDF、标注、Review 与 Community。
- [私有标注与评审](annotations-and-reviews.md)：Zotero 主模式与 Obsidian
  兼容模式的数据所有权。
- [PDF 版本](pdf-versioning.md)与 [PDF++ 集成](pdf-plus-integration.md)。
- [论文图片](论文图片处理说明.md)、[实体导航](entity-navigation.md)和
  [中文属性显示](中文属性显示说明.md)。

### AI 与自动化

- [AI Provider](ai-providers.md)与 [ChatGPT Web 隐私](ChatGPT网页分析与隐私.md)。
- [Obsidian Automation](automation.md)与[控制中心](control-center.md)。
- [Zotero AI Markdown](zotero-ai-markdown.md)。
- [Zotero 迁移与只读 Local API](zotero-migration.md)。

### 订阅与社区

- [公共 Feed](public-feed.md)、[订阅 Feed](subscribing-to-feeds.md)和
  [发布 Feed](publishing-a-feed.md)。
- [社区贡献](community-contributions.md)、[社区订阅](community-subscriptions.md)
  与[隐私/版权](community-privacy-copyright.md)。
- [程序与数据仓库分离](repository-separation.md)。

## 运维与升级

1. [配置](configuration.md)
2. [迁移机制](migrations.md)
3. [1.5 迁移指南](1.5-migration-guide.md)
4. [升级](upgrading.md)
5. [故障排查](troubleshooting.md)
6. [Nutstore 同步兼容](Nutstore兼容建议.md)
7. [发布](releasing.md)

平台安装说明位于 [Windows](installation/windows.md)、
[macOS](installation/macos.md) 和 [Linux](installation/linux.md)。

## 维护者参考

- [用户与维护者指南：维护者部分](维护者与用户指南.md#维护者指南)
- [架构与数据层](architecture.md)
- [数据模型](data-model.md)
- [Artifact 权限](artifact-permissions.md)
- [安全边界](security.md)
- [路径模板](path-templates.md)
- [验证矩阵](verification-matrix.md)
- [代表性具身智能与触觉样本](首批具身智能与触觉论文样本.md)
- Zotero 验收证据：
  [主工作流](audits/zotero-primary-workflow-audit.md)、
  [隔离 Profile](audits/zotero-test-profile.md)、
  [本机环境](audits/zotero-local-environment-audit.md)

## 历史资料

[archive/](archive/README.md) 包含 PaperFlow 1.4 文档、1.5 阶段性实现快照和
已完成的设计/迁移审计。这些页面保留用于追溯，不参与当前操作说明。

## 文档维护规则

- 一个主题只保留一个当前权威页面；其他页面应链接过去或进入 `archive/`。
- 日期、测试数量和真实环境证据集中写入验证矩阵或带日期的审计，不在多个指南中复制。
- 用户流程写“怎么用”，架构写“为什么这样工作”，运维文档写“怎么恢复”。
- 新增或移动页面后必须验证全部相对链接；历史页面必须带明确的历史标记。
