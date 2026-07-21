# 标注与社区功能维护手册

## 版本契约

1.5.0：Workspace 3、Feed 2、Annotation 1、Community 1、模板 5、
`paper-analysis-v3`。应用版本只修改 `src/paperflow/_version.py`；构建与 CI
必须核对 pyproject 动态版本、插件 manifest、tag 和 minimum reader。

## 代码

- `annotations/`：models/store/parser/renderer/selectors/anchors/reanchor/
  importers/pdf_versions/service。
- `community/`：models/privacy/publisher/subscriber/preferences。
- `cli_features.py`：保持 `paperflow.cli:app` 的模块化子命令。
- `workspace_v3.py`：备份、PDF 复制、索引、路径和 Bases 迁移。
- `integrations/obsidian-pdf-plus`：只包含兼容声明与配置建议。

## 强制回归

```powershell
python -m compileall -q src
python -m pytest
node tests/integration/test_scheduler_core.js
node tests/integration/test_automation_plugin_lifecycle.js
python scripts/build_release.py
python -m pytest tests/packaging
paperflow migrate workspace-v3 --dry-run --vault <vault>
paperflow doctor
paperflow audit
```

插件修改后用 Obsidian CLI reload、`dev:errors`、`dev:console level=error`、
DOM 和截图复验。Base 变更必须验证每个 Base；路径变更必须验证全部 wikilink
和附件。真实贡献 PR、Feed push、软件 release 和许可改变都需要单独授权。
