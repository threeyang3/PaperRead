# PaperFlow 1.4 维护者指南

> 历史文档：保留用于旧版本维护。当前开发、测试与发布契约见
> [PaperFlow 用户与维护者指南](../../维护者与用户指南.md#维护者指南)。

## 仓库边界

- `PaperRead`：MIT 许可的软件源码、测试、schemas、migrations、prompts、模板、Obsidian 集成和文档。
- `ArXiv-data`：CC BY 4.0 的可订阅 Feed 数据。
- 用户 Vault：论文、PDF、图片、阅读笔记、用户属性、运行状态和本地配置。

源码应位于 Vault 外的独立仓库。Vault 插件只启动 `.paperflow/.venv` 中已安装的 PaperFlow，不回退到 Vault 根目录 `src`。发布物使用正向白名单，禁止带入论文、PDF、用户笔记、浏览器配置、日志、缓存、数据库和 Obsidian 工作区状态。

## 版本契约

PaperFlow 1.4.0 使用 Workspace schema 2、论文模板 v5、`paper-analysis-v3`。新增平面 YAML 字段时，必须同时更新 schema、模板、迁移、测试和文档。Prompt 变化必须提升 prompt 版本，数据布局变化必须通过正式迁移。

1.4 迁移：

```powershell
paperflow migrate workspace-v2 --dry-run
paperflow migrate workspace-v2 --apply
paperflow migrate verify-workspace-v2
```

迁移会完整备份 Workspace，安装受管资源，通过 `compose_record()` 合成 Raw、AI、User、Derived 四层，再安全重渲染生成笔记。不得批量手工改写论文笔记。

## 写入和同步安全

所有生成笔记在计算前记录 SHA256，写入前再次核验。发生外部修改时拒绝覆盖并生成 Manual Review。插件的静态设置保存在 `data.json`，高频作业状态保存在 `.paperflow/runtime/plugin-state.json`。任何 `-冲突` 或 `-NSConflict` 文件都应视为暂停信号。

Raw 和 AI 记录不可变。重新抓取的不同 Raw 元数据只有在明确允许保留旧 Raw 时，才追加到 `vN/captures/<time>-<hash>.json`，Derived 记录当前选中的 capture。

## 测试

每次代码改动必须运行：

```powershell
python -m compileall -q src
python -m pytest
node tests/integration/test_automation_plugin_lifecycle.js
node tests/integration/test_scheduler_core.js
python scripts/build_release.py
python -m pytest tests/packaging/test_artifacts.py
paperflow doctor
paperflow audit
paperflow health
```

Obsidian 插件变更还必须重载插件、检查开发者控制台错误，并验证控制中心 DOM/截图。涉及路径或 Base 时，额外运行全部 wikilink、附件路径和 Base 校验。

## 发布物

- wheel / sdist；
- `PaperFlow-Template-Vault-<version>.zip`；
- `PaperFlow-portable-<version>.zip`；
- `SHA256SUMS`。

CI 和本地构建共同审计发布物。Feed v1 保持向后兼容，数据源构建只读取已选择的可信 Raw capture。
