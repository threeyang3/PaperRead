# 标注与社区故障排查

- **PDF++ 未安装**：`integration pdf-plus status`；可继续使用原生 page link。
- **PDF++ 设置冲突**：合并 `data.json.new`，不要删除用户自定义值。
- **标注/sidecar 冲突**：保留双方，运行 `annotation validate`，进入 Manual Review。
- **标注失效**：先 `annotation reanchor ... --dry-run`；manual-review 不可强制发布。
- **PDF hash 不匹配**：确认版本路径，不覆盖原文件；从可信来源另存新版本。
- **社区记录被拒绝**：运行 `community publish scan`，移除路径、邮箱、凭据、
  HTML/危险 URI、图片/PDF 或超长引用。
- **`content_sha256 mismatch`**：远端贡献内容与发布快照不一致；不要手工修正
  哈希或绕过校验，应从可信发布者重新获取原始 revision。
- **社区评分和个人评分不同**：这是设计行为；两者永不合并。
- **Feed v2 提示升级**：升级 reader，不手改 `feed_schema_version`。
- **同步未显示社区**：确认 subscription capabilities 包含 community；旧配置默认
  只有 raw/ai。
- **Nutstore 冲突**：停止 PaperFlow，等待同步稳定，保留冲突副本后人工合并。
