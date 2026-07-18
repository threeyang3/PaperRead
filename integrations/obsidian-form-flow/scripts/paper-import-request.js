async function entry() {
  const { app, form, obsidian, Notice, moment } = this.$context;
  const rawPriority = Number(form["优先级"] ?? 3);
  const priority = Number.isFinite(rawPriority) ? Math.max(1, Math.min(5, Math.trunc(rawPriority))) : 3;
  const paperInput = String(form["论文链接或 ID"] ?? "").trim();
  if (!paperInput) throw new Error("论文链接或 ID 不能为空");
  const requestId = crypto.randomUUID();
  const beijing = moment().utcOffset(480);
  const createdAt = beijing.format("YYYY-MM-DDTHH:mm:ssZ");
  const stamp = beijing.format("YYYYMMDD-HHmmss");
  const tags = String(form["用户标签"] ?? "").split(",").map(v => v.trim()).filter(Boolean);
  const detectedLocale = String(globalThis.localStorage?.getItem("language") || moment.locale() || "en");
  const uiLocale = detectedLocale.toLowerCase().startsWith("zh") ? "zh-CN" : "en";
  const data = {
    type: "paper-import-request", schema_version: 1, request_id: requestId,
    paper_input: paperInput, topic_hint: String(form["主题提示"] ?? "").trim(), priority,
    add_to_reading_queue: Boolean(form["加入阅读队列"] ?? true), favorite: Boolean(form["收藏"] ?? false),
    user_tags: tags, run_ai: Boolean(form["立即进行 AI 分析"] ?? true), ui_locale: uiLocale, status: "pending",
    created_at: createdAt, processed_at: null, result_paper_uid: null, result_note: null, error: null
  };
  const yaml = obsidian.stringifyYaml(data).trimEnd();
  const note = String(form["备注"] ?? "");
  const content = `---\n${yaml}\n---\n\n# 论文导入请求\n\n## 用户备注\n\n${note}\n`;
  const path = `50 Inbox/Paper Requests/${stamp}-${requestId}.md`;
  await app.vault.create(path, content);
  new Notice(`论文导入请求已创建：${requestId}`);
}

exports.default = {
  entry,
  name: "PaperImportRequest",
  description: "在固定 Inbox 中创建经过类型规范化的 PaperFlow 请求，不执行外部命令。",
  tags: ["paperflow", "safe-request"]
};
