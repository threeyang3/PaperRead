# PDF、社区与标注现状审计

> 2026-07-20 历史审计快照，不代表当前实现状态。

审计日期：2026-07-20（Asia/Shanghai）。

## 审计范围

- 程序仓库：`E:/PaperRead`，分支 `agent/paperflow-1.4`，审计前 HEAD
  `492faa6`。
- 唯一目标 Vault：`E:/ObsidianVaults/ArxivLearn`。
- 数据仓库工作副本：
  `E:/ObsidianVaults/ArxivLearn/.paperflow/publish/feed`，远端
  `threeyang3/ArXiv-data`。

## 基线

| 项目 | 审计值 |
| --- | ---: |
| 论文记录/笔记 | 30 / 30 |
| 本地 PDF 文件 | 60 |
| Raw / AI / User / Derived | 86 / 86 / 30 / 30 |
| Feed Raw / AI | 30 / 30 |
| Feed schema | 1 |
| Workspace schema | 2 |
| 应用/插件版本 | 1.4.0 / 1.4.0 |

60 个 PDF 包含当前路径与历史/派生布局中的重复对象，不能据此推断 60 篇论文。
迁移必须按论文记录的当前 `paper_pdf_path` 和 SHA-256 逐项处理。

## 发现

1. 应用版本在 Python、`pyproject.toml`、构建脚本和插件 manifest 中重复。
2. 默认 PDF 路径是 `{{year}}/{{paper_id}}.pdf`，新版本可能覆盖旧版本。
3. 没有独立 PDF hash index、稳定标注协议或重定位修订记录。
4. Feed v1 只表达 Raw/AI，不能能力协商社区层。
5. User、AI、社区意见和评分没有完整的物理/语义分层。
6. 控制中心已有非线性任务入口，但没有阅读、标注、评审、社区和贡献发布入口。
7. PDF++ 未安装；原 Vault 不存在 `.obsidian/plugins/pdf-plus`。
8. ArXiv-data 工作区干净，Raw/AI 路径可保持不变后扩展 Feed v2。

## 决策

- 1.5.0 使用 `_version.py` 作为应用单一版本源；Workspace schema 3、
  Feed schema 2、Annotation schema 1、Community schema 1。
- PDF 路径升级为
  `80 Attachments/Papers/{{year}}/{{paper_id}}/v{{version}}.pdf`，迁移复制
  而不删除旧 PDF。
- 个人标注和评审始终是私有 User 数据；社区只能来自用户显式选择的不可变、
  脱敏快照。
- PDF++ 作为推荐适配器，未安装时退化为原生页码链接。PaperFlow 不调用
  PDF++ 私有 API，且默认关闭 PDF 直接编辑。
- Feed v2 保留 v1 Raw/AI 路径；社区按论文拆分 manifest，发布默认关闭。
- 真实公共贡献 PR 不在本轮自动执行；只验证本地 outbox、隐私扫描和 PR dry-run。
