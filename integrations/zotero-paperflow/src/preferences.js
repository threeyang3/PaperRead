/* global Zotero */
"use strict";

var PaperFlowPreferences = {
  document: null,
  busy: false,
  bridge() {
    if (!Zotero.PaperFlowPreferences) throw new Error("PaperFlow 插件未启动，请重启 Zotero");
    return Zotero.PaperFlowPreferences;
  },
  field(name) { return this.document.getElementById(`paperflow-prefs-${name}`); },
  message(value) { this.field("status").textContent = value; },
  init(doc) {
    this.document = doc;
    const bridge = this.bridge();
    this.field("url").value = bridge.get("extensions.paperflow-zotero.coreBaseUrl", "http://127.0.0.1:23140");
    this.field("profile").value = bridge.get("extensions.paperflow-zotero.analysisProfile", "full_analysis");
    this.field("debounce").value = Number(bridge.get("extensions.paperflow-zotero.eventDebounceMs", 10000)) / 1000;
    this.field("token").value = "";
    this.message(bridge.get("extensions.paperflow-zotero.pairingId", "")
      ? "本机配对已保存；点击检查连接确认 Core 状态。" : "尚未配对。请粘贴会话令牌并连接。");
  },
  options() {
    const baseUrl = this.bridge().validateUrl(this.field("url").value.trim());
    const profile = this.field("profile").value;
    if (!["full_analysis", "triage"].includes(profile)) throw new Error("请选择有效的分析配置");
    const seconds = Number(this.field("debounce").value);
    if (!Number.isInteger(seconds) || seconds < 1 || seconds > 300) throw new Error("等待时间必须为 1–300 秒的整数");
    return { baseUrl, profile, debounce: seconds * 1000 };
  },
  apply(options) {
    const bridge = this.bridge();
    if (options.baseUrl !== bridge.get("extensions.paperflow-zotero.coreBaseUrl", "http://127.0.0.1:23140")) {
      // Pairing credentials belong to one Core endpoint only.
      for (const key of ["coreToken", "pairingId", "pairingSecret"]) bridge.set(`extensions.paperflow-zotero.${key}`, "");
    }
    bridge.set("extensions.paperflow-zotero.coreBaseUrl", options.baseUrl);
    bridge.set("extensions.paperflow-zotero.analysisProfile", options.profile);
    bridge.set("extensions.paperflow-zotero.eventDebounceMs", options.debounce);
    bridge.changed();
    this.field("url").value = options.baseUrl;
  },
  save() {
    if (this.busy) return;
    try {
      this.apply(this.options());
      this.message("设置已保存；地址如有变化，请重新连接并配对。");
    } catch (error) { this.message(error.message || String(error)); }
  },
  async run(action) {
    if (this.busy) return;
    this.busy = true;
    for (const id of ["connect", "check", "save"]) this.field(id).disabled = true;
    this.message("正在连接本机 Core…");
    try { await action(); }
    catch (error) { this.message(`连接失败：${error.message || error}`); }
    finally {
      this.busy = false;
      for (const id of ["connect", "check", "save"]) this.field(id).disabled = false;
    }
  },
  async connect() {
    return this.run(async () => {
      const options = this.options();
      const token = this.field("token").value.trim();
      if (!token) throw new Error("请先粘贴 Core 会话令牌");
      try {
        const result = await this.bridge().connect(options.baseUrl, token);
        this.apply(options);
        this.message(result.message);
      } finally { this.field("token").value = ""; }
    });
  },
  async check() {
    return this.run(async () => {
      const bridge = this.bridge();
      const value = bridge.validateUrl(this.field("url").value.trim());
      if (value !== bridge.get("extensions.paperflow-zotero.coreBaseUrl", "http://127.0.0.1:23140")) {
        throw new Error("地址尚未保存，请先连接并配对");
      }
      const result = await bridge.status();
      this.message(result.message);
    });
  },
  importPaper() { return this.bridge().importPaper(); },
  openControlCenter() { return this.bridge().openControlCenter(); },
  async loadJobs() {
    return this.run(async () => {
      const value = await this.bridge().jobs();
      this.renderJobs(value.jobs || []);
      this.message(`已刷新 ${value.jobs?.length || 0} 个作业。`);
    });
  },
  renderJobs(jobs) {
    const container = this.field("jobs");
    container.textContent = "";
    const doc = this.document;
    for (const job of jobs) {
      const row = doc.createElementNS("http://www.w3.org/1999/xhtml", "div");
      row.style.cssText = "padding:8px 0;border-bottom:1px solid #8884";
      const text = doc.createElementNS("http://www.w3.org/1999/xhtml", "p");
      const date = new Date(job.updated_at || job.created_at);
      const time = Number.isFinite(date.getTime()) ? date.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "时间未知";
      text.textContent = `${time} · ${job.kind} · ${job.status}\n${job.paper_uid || "全库任务"}`;
      text.style.whiteSpace = "pre-line";
      row.appendChild(text);
      if (job.error) {
        const error = doc.createElementNS("http://www.w3.org/1999/xhtml", "p");
        error.textContent = String(job.error).slice(0, 1000);
        row.appendChild(error);
      }
      const action = ["failed", "interrupted", "cancelled", "skipped"].includes(job.status) ? "retry"
        : ["queued", "running"].includes(job.status) ? "cancel" : "";
      if (action) {
        const button = doc.createElementNS("http://www.w3.org/1999/xhtml", "button");
        button.textContent = action === "retry" ? "按当前配置重试" : "取消任务";
        button.addEventListener("click", async () => {
          await this.run(async () => {
            button.disabled = true;
            try {
              const result = await this.bridge().jobAction(job.job_id, action);
              this.message(`作业 ${result.job_id}：${result.status}`);
              this.renderJobs((await this.bridge().jobs()).jobs || []);
            } finally { button.disabled = false; }
          });
        });
        row.appendChild(button);
      }
      container.appendChild(row);
    }
  },
};
