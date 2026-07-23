# Zotero AI Markdown 投影

`paperflow zotero render-ai --paper arxiv:2504.16054` 生成的是 AI Raw 的读者视图，不是
第二份可编辑事实源：

- YAML 保存标题、作者、日期、URL、状态和 Zotero item key；正文只呈现摘要、贡献、方法、
  证据、局限和费曼问题，避免把作者/主页等元数据再次复制到正文。
- 投影标记为 `artifact_permission: SYSTEM_MANAGED`，写入前计算内容哈希；已有内容不同
  时返回 `manual-review-required`，不覆盖用户修改。
- Vault 模式默认写入 `.paperflow/data/zotero/markdown/`；独立 Core Data Root 模式写入
  `documents/zotero/`。`attach-ai-markdown` 只生成由 Zotero 插件调用附件 API 的计划，
  Core 不直接写 Zotero。
- 可用 `--target zotero|obsidian|both` 选择投影目标；`both` 会同时生成 Zotero 与
  Obsidian 系统文件，并在 `data/derived/ai-render-state/` 保存单一 primary writer、内容
  哈希和目标状态。任一目标被用户修改时，重渲染都返回 `manual-review-required`。
- Zotero 插件手动分析会读取本机 `analysisTarget` 偏好并把目标传给 Core；Core 在分析
  完成后按同一目标渲染，避免分析结果和 Markdown 投影由两个写入器竞争。
- Obsidian 的 AI Markdown、个人笔记、费曼答案、复盘和复现仍是独立目标；AI Raw 更新
  不会覆盖用户输出。

费曼问题可执行 `paperflow zotero feynman init --paper <uid> --apply` 投影到独立的用户答案文件；答案写入 `.paperflow/data/user/feynman/`（standalone Core 为 `data/user/feynman/`），属于 `USER_MANAGED`，不会被 AI 重分析、订阅更新或 Markdown 重渲染覆盖。
