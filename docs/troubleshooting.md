# Troubleshooting

Run these in order:

```text
paperflow config doctor
paperflow doctor
paperflow workspace validate
paperflow paths validate
paperflow migrate status
paperflow integration status form-flow
```

If configuration is invalid, the error identifies the field, current value,
and file to edit. If data is newer than the installed reader, upgrade the
application rather than forcing a write. If migration fails, inspect
`.paperflow/state/migrations/history.jsonl`; the run snapshot remains under
`.paperflow/backups`.

For Form Flow conflicts, review the existing file and its `.new` candidate.
PaperFlow deliberately does not overwrite the customized file.

If a visual guide is missing, confirm the paper has a local PDF, run
`paperflow paper visuals <paper_uid>`, then run `paperflow validate`. A
`no-captioned-figures` result means no reliable `Figure`/`Fig.` caption was
found; PaperFlow intentionally does not fabricate a diagram.

If an architecture figure is incomplete or a crop includes adjacent text, open
the PDF-page link below the image to compare it with the source, then rerun with
the adaptive defaults or a `--max-assets 0..12` safety ceiling. Extracted images are Derived, so rerunning is
safe and does not overwrite User Data.

## Zotero 与 Core

- **连接返回 401**：确认 Core 仍绑定 `127.0.0.1`，重新执行一次“连接 Core”。
  成功配对后，后续 Core 重启应自动续期 session，不需要保存长期 bearer token。
- **菜单没有响应或仍显示旧错误**：先正常重启 Zotero，使 bootstrap 与子模块同时
  重新加载；不要编辑 `extensions.json` 或 Zotero 数据库。
- **导入成功但 AI Markdown 尚未出现**：导入和分析/渲染是两个作业阶段。先查看
  Core 作业状态；完成后仍缺失时，选择论文运行“附加 AI Markdown”恢复动作。
- **Reader 评论没有进入镜像**：选择论文、PDF 或标注，运行“同步选中论文标注”。
  新 Zotero 标注只生成 SYSTEM_MANAGED JSON，不会新建旧式 Obsidian Annotation Note。
- **mapping 与当前条目不一致**：选择当前论文运行“同步身份与附件校验”，再检查
  attachment SHA-256 状态。Core 不直接修正 Zotero 数据库。

## 标注与社区

- **PDF++ 未安装**：运行 `paperflow integration pdf-plus status`；原生页码链接仍可用。
- **标注/sidecar 冲突**：保留双方，运行 `paperflow annotation validate`，进入
  Manual Review。
- **标注失效或 PDF hash 不匹配**：先运行 `annotation reanchor ... --dry-run`，
  不覆盖旧版本 PDF 或强制发布 manual-review 内容。
- **社区记录或 `content_sha256` 被拒绝**：运行 `community publish scan`；移除
  路径、邮箱、凭据、活动 HTML、危险 URI、图片/PDF 或超长引用。不要手工改哈希。
- **同步后没有社区内容**：确认订阅 capabilities 包含 `community`；旧配置默认
  只有 Raw/AI。
- **Nutstore 冲突**：停止 PaperFlow，等待同步稳定，保留冲突副本后人工合并。
