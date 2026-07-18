"use strict";

const {
  Plugin,
  PluginSettingTab,
  Setting,
  Notice,
  Platform,
  ItemView,
  Modal,
  setIcon
} = require("obsidian");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const TIME_ZONE = "Asia/Shanghai";
const CONTROL_VIEW_TYPE = "paperflow-control-center";

function beijingClock(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23"
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return {
    date: `${values.year}-${values.month}-${values.day}`,
    time: `${values.hour}:${values.minute}:${values.second}`,
    minutes: Number(values.hour) * 60 + Number(values.minute)
  };
}

function parseLocalTime(value) {
  const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(String(value || ""));
  if (!match) throw new Error(`无效的每日时间：${value}`);
  return Number(match[1]) * 60 + Number(match[2]);
}

function shouldRunDaily(settings, now = new Date()) {
  const clock = beijingClock(now);
  return {
    due:
      Boolean(settings.catchUpDailyAfterStartup) &&
      clock.minutes >= parseLocalTime(settings.dailyLocalTime) &&
      settings.runtime.lastDailyDate !== clock.date,
    clock
  };
}

function jobArguments(kind) {
  if (kind === "inbox") return ["-m", "paperflow.cli", "inbox"];
  if (kind === "daily") return ["-m", "paperflow.cli", "daily"];
  if (kind === "source-sync") {
    return ["-m", "paperflow.cli", "source", "sync", "--all"];
  }
  if (kind === "publish-auto") {
    return [
      "-m", "paperflow.cli", "publish", "auto",
      "--push", "--confirm-automation"
    ];
  }
  if (kind === "update-auto") {
    return ["-m", "paperflow.cli", "update", "auto"];
  }
  throw new Error(`未知 PaperFlow 作业：${kind}`);
}

function intervalDue(lastAt, intervalMinutes, now = Date.now()) {
  const interval = Math.max(1, Number(intervalMinutes) || 1) * 60 * 1000;
  const previous = Date.parse(String(lastAt || ""));
  return !Number.isFinite(previous) || now - previous >= interval;
}

function isInboxRequestPath(value) {
  const normalized = String(value || "").replaceAll("\\", "/");
  return (
    normalized.startsWith("50 Inbox/Paper Requests/") &&
    normalized.toLowerCase().endsWith(".md")
  );
}

function cleanText(value, label, maximum = 300) {
  const result = String(value || "").trim();
  if (!result) throw new Error(`${label}不能为空。`);
  if (result.length > maximum || /[\u0000-\u001f\u007f]/.test(result)) {
    throw new Error(`${label}包含无效字符或过长。`);
  }
  return result;
}

function safeName(value, label = "名称") {
  const result = cleanText(value, label, 80);
  if (!/^[A-Za-z0-9._-]+$/.test(result)) {
    throw new Error(`${label}只能包含字母、数字、点、下划线和连字符。`);
  }
  return result;
}

function githubUrl(value) {
  const parsed = new URL(cleanText(value, "GitHub URL", 500));
  const parts = parsed.pathname.split("/").filter(Boolean);
  if (
    parsed.protocol !== "https:" ||
    parsed.hostname.toLowerCase() !== "github.com" ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    parts.length !== 2
  ) {
    throw new Error("请输入 https://github.com/<owner>/<repository> 格式的链接。");
  }
  const repository = parts[1].endsWith(".git")
    ? parts[1].slice(0, -4)
    : parts[1];
  if (!repository) throw new Error("GitHub 仓库名不能为空。");
  return `https://github.com/${parts[0]}/${repository}.git`;
}

function optionalHttpsUrl(value, label) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const parsed = new URL(raw);
  if (
    parsed.protocol !== "https:" ||
    !parsed.hostname ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash
  ) {
    throw new Error(`${label}必须是不含凭证、查询或锚点的 HTTPS URL。`);
  }
  return parsed.toString();
}

function branchName(value) {
  const result = cleanText(value, "Git 分支", 120);
  if (
    !/^[A-Za-z0-9._/-]+$/.test(result) ||
    result.includes("..") ||
    result.startsWith("/") ||
    result.endsWith("/")
  ) {
    throw new Error("Git 分支名称无效。");
  }
  return result;
}

function profileName(value) {
  const result = String(value || "");
  const allowed = new Set([
    "triage",
    "full_analysis",
    "fallback_analysis",
    "reanalysis"
  ]);
  if (!allowed.has(result)) throw new Error(`未知 AI profile：${result}`);
  return result;
}

function providerName(value) {
  const result = String(value || "");
  if (!new Set(["codex", "claude", "mock"]).has(result)) {
    throw new Error(`未知 AI provider：${result}`);
  }
  return result;
}

function controlCommands(action, payload = {}) {
  switch (action) {
    case "status":
      return [["status"]];
    case "doctor":
      return [["doctor"]];
    case "inbox":
      return [["inbox"]];
    case "daily":
      return [["daily"]];
    case "discover":
      return [["discover"]];
    case "paper-add": {
      const value = cleanText(payload.value, "论文链接或 ID", 1000);
      const priority = Math.min(5, Math.max(1, Number(payload.priority) || 3));
      return [[
        "paper", "add", value, "--priority", String(priority),
        payload.ai === false ? "--no-ai" : "--ai"
      ]];
    }
    case "paper-analyze": {
      const paperUid = cleanText(payload.paperUid, "Paper UID", 300);
      const provider = String(payload.provider || "configured");
      if (!new Set(["configured", "codex", "claude", "mock"]).has(provider)) {
        throw new Error(`未知 AI provider：${provider}`);
      }
      const command = ["paper", "analyze", paperUid];
      if (provider !== "configured") command.push("--provider", provider);
      return [command];
    }
    case "ai-save": {
      const profile = profileName(payload.profile);
      const provider = providerName(payload.provider);
      const model = String(payload.model || "").trim();
      const timeout = Math.min(14400, Math.max(1, Number(payload.timeout) || 1800));
      const reasoningEffort = String(payload.reasoningEffort || "");
      if (!new Set(["", "low", "medium", "high", "xhigh"]).has(reasoningEffort)) {
        throw new Error(`未知推理强度：${reasoningEffort}`);
      }
      const reanalyzeWhen = String(payload.reanalyzeWhen || "identity-changed");
      if (!new Set(["identity-changed", "never", "always"]).has(reanalyzeWhen)) {
        throw new Error(`未知重新分析策略：${reanalyzeWhen}`);
      }
      if (model.length > 200 || /[\u0000-\u001f\u007f]/.test(model)) {
        throw new Error("模型名称包含无效字符或过长。");
      }
      return [[
        "ai",
        "set-profile",
        profile,
        "--provider",
        provider,
        "--model",
        model,
        "--timeout",
        String(timeout),
        "--reasoning-effort",
        reasoningEffort,
        payload.fallback ? "--fallback" : "--no-fallback",
        payload.reuseFeed === false ? "--no-reuse-feed" : "--reuse-feed",
        "--reanalyze-when",
        reanalyzeWhen
      ]];
    }
    case "ai-test":
      return [["ai", "test", "--profile", profileName(payload.profile)]];
    case "ai-providers":
      return [["ai", "providers"]];
    case "ai-profiles":
      return [["ai", "profiles"]];
    case "source-list":
      return [["source", "list"]];
    case "source-status":
      return [["source", "status"]];
    case "source-add":
      return [[
        "source",
        "add",
        githubUrl(payload.url),
        "--name",
        safeName(payload.name, "订阅名称")
      ]];
    case "source-inspect":
      return [["source", "inspect", safeName(payload.name, "订阅名称")]];
    case "source-sync":
      return [["source", "sync", safeName(payload.name, "订阅名称")]];
    case "source-sync-all":
      return [["source", "sync", "--all"]];
    case "source-disable":
      return [["source", "disable", safeName(payload.name, "订阅名称")]];
    case "source-remove":
      return [["source", "remove", safeName(payload.name, "订阅名称")]];
    case "source-trust": {
      const mode = String(payload.mode || "metadata-and-ai");
      if (!new Set(["metadata-only", "metadata-and-ai", "disabled"]).has(mode)) {
        throw new Error(`未知订阅信任模式：${mode}`);
      }
      return [[
        "source", "trust", safeName(payload.name, "订阅名称"), mode
      ]];
    }
    case "publish-status":
      return [["publish", "status"]];
    case "publish-plan":
      return [["publish", "plan"]];
    case "publish-build":
      return [["publish", "build"]];
    case "publish-configure": {
      const remote = String(payload.remote || "").trim();
      return [[
        "publish",
        "configure",
        "--feed-id",
        safeName(payload.feedId, "Feed ID"),
        "--name",
        cleanText(payload.name, "Feed 名称", 300),
        "--publisher-name",
        cleanText(payload.publisherName, "发布者名称", 300),
        "--publisher-url",
        optionalHttpsUrl(payload.publisherUrl, "发布者 URL"),
        "--data-license",
        cleanText(payload.dataLicense, "数据许可证", 300),
        "--repository-url",
        remote ? githubUrl(remote) : "",
        "--branch",
        branchName(payload.branch || "main")
      ]];
    }
    case "publish-validate":
      return [["publish", "validate"]];
    case "publish-scan":
      return [["publish", "scan"]];
    case "publish-snapshot":
      return [["publish", "snapshot"]];
    case "git-init":
      return [["publish", "git-init", "--remote", githubUrl(payload.remote)]];
    case "git-status":
      return [["publish", "git-status"]];
    case "git-commit":
      return [[
        "publish",
        "commit",
        "--message",
        cleanText(payload.message, "提交说明", 200)
      ]];
    case "git-push":
      return [["publish", "push", "--confirm"]];
    case "publish-auto":
      return [[
        "publish", "auto", "--push", "--confirm-automation"
      ]];
    case "workspace-backup":
      return [["workspace", "backup"]];
    case "workspace-info":
      return [["workspace", "info"]];
    case "workspace-validate":
      return [["workspace", "validate"]];
    case "workspace-repair-preview":
      return [["workspace", "repair", "--dry-run"]];
    case "migrate-status":
      return [["migrate", "status"]];
    case "migrate-plan":
      return [["migrate", "plan"]];
    case "migrate-verify":
      return [["migrate", "verify"]];
    case "paths-validate":
      return [["paths", "validate"]];
    case "paths-preview":
      return [["paths", "preview"]];
    case "render-preview":
      return [["paper", "render-all", "--dry-run"]];
    case "validate-all":
      return [["validate"]];
    case "retry-failed":
      return [["retry-failed"]];
    case "rebuild-index":
      return [["rebuild-index"]];
    case "rebuild-bases":
      return [["rebuild-bases"]];
    case "config-validate":
      return [["config", "validate"]];
    case "config-show":
      return [["config", "show", "--resolved"]];
    case "form-flow-status":
      return [["integration", "status", "form-flow"]];
    case "update-check":
      return [["update", "check"]];
    case "update-save":
      return [[
        "update",
        "configure",
        "--repository-url",
        githubUrl(payload.repository),
        payload.autoCheck === false ? "--no-auto-check" : "--auto-check",
        payload.autoStage === false ? "--no-auto-stage" : "--auto-stage"
      ]];
    case "update-stage":
      return [["update", "stage"]];
    case "update-apply":
      return [["update", "apply", "--confirm"]];
    default:
      throw new Error(`不允许的 PaperFlow 操作：${action}`);
  }
}

const DEFAULT_SETTINGS = {
  enabled: true,
  openControlCenterOnStartup: true,
  inboxIntervalMinutes: 5,
  inboxEventDebounceMs: 1500,
  dailyLocalTime: "08:00",
  catchUpDailyAfterStartup: true,
  sourceSyncEnabled: true,
  sourceSyncIntervalMinutes: 60,
  autoPublishEnabled: false,
  autoPublishIntervalMinutes: 60,
  updateCheckEnabled: true,
  updateCheckIntervalMinutes: 360,
  pythonExecutable: "python",
  preferVaultPython: true,
  pythonRelativePath: ".paperflow/.venv/Scripts/python.exe",
  controlCenter: {
    paperValue: "",
    paperPriority: 3,
    paperUseAi: true,
    analyzePaperUid: "",
    analyzeProvider: "configured",
    aiProfile: "full_analysis",
    aiProvider: "codex",
    aiModel: "",
    aiTimeout: 1800,
    aiReasoningEffort: "high",
    aiFallback: false,
    aiReuseFeed: true,
    aiReanalyzeWhen: "identity-changed",
    sourceName: "community-feed",
    sourceUrl: "",
    publishFeedId: "",
    publishName: "",
    publisherName: "",
    publisherUrl: "",
    dataLicense: "",
    publishBranch: "main",
    publishRemote: "",
    commitMessage: "Update PaperFlow Feed",
    sourceTrust: "metadata-and-ai",
    updateRepository: "https://github.com/threeyang3/PaperRead",
    updateAutoStage: true
  },
  runtime: {
    lastDailyDate: "",
    lastDailyAt: "",
    lastDailyExitCode: null,
    lastInboxAt: "",
    lastInboxExitCode: null,
    lastSourceSyncAt: "",
    lastSourceSyncExitCode: null,
    lastPublishAt: "",
    lastPublishExitCode: null,
    lastUpdateCheckAt: "",
    lastUpdateCheckExitCode: null,
    updateAvailableVersion: "",
    lastMessage: "",
    lastControlAt: "",
    lastControlAction: "",
    lastControlExitCode: null,
    lastControlOutput: ""
  }
};

function isChinese() {
  const locale =
    globalThis.localStorage?.getItem("language") ||
    globalThis.moment?.locale?.() ||
    "en";
  return String(locale).toLowerCase().startsWith("zh");
}

function text(zh, en) {
  return isChinese() ? zh : en;
}

function mergedSettings(value) {
  return {
    ...DEFAULT_SETTINGS,
    ...(value || {}),
    runtime: {
      ...DEFAULT_SETTINGS.runtime,
      ...((value || {}).runtime || {})
    },
    controlCenter: {
      ...DEFAULT_SETTINGS.controlCenter,
      ...((value || {}).controlCenter || {})
    }
  };
}

class PaperFlowAutomationPlugin extends Plugin {
  async onload() {
    this.settings = mergedSettings(await this.loadData());
    this.runningJob = null;
    this.inboxEventTimer = null;
    this.controlSaveTimer = null;
    this.started = false;
    this.statusBar = this.addStatusBarItem();
    this.updateStatus(text("PaperFlow 自动化：等待启动", "PaperFlow automation: waiting"));

    this.registerView(
      CONTROL_VIEW_TYPE,
      (leaf) => new PaperFlowControlCenterView(leaf, this)
    );
    this.addRibbonIcon(
      "library-big",
      text("打开 PaperFlow 控制中心", "Open PaperFlow Control Center"),
      () => void this.activateControlCenter()
    );
    this.addCommand({
      id: "open-control-center",
      name: text("打开控制中心", "Open Control Center"),
      callback: () => void this.activateControlCenter()
    });
    this.addCommand({
      id: "run-inbox-now",
      name: text("立即处理 Inbox", "Process Inbox now"),
      callback: () => this.runJob("inbox", "manual")
    });
    this.addCommand({
      id: "run-daily-now",
      name: text("立即运行每日流程", "Run daily workflow now"),
      callback: () => this.runJob("daily", "manual")
    });
    this.addCommand({
      id: "show-status",
      name: text("显示自动化状态", "Show automation status"),
      callback: () => new Notice(this.statusSummary(), 10000)
    });
    this.addSettingTab(new PaperFlowAutomationSettingTab(this.app, this));

    this.app.workspace.onLayoutReady(async () => {
      await this.startAutomation();
      if (this.settings.openControlCenterOnStartup) {
        try {
          await this.activateControlCenter();
        } catch (error) {
          new Notice(
            text(
              `PaperFlow 控制中心未能自动打开：${error.message}`,
              `PaperFlow Control Center could not open automatically: ${error.message}`
            ),
            12000
          );
        }
      }
    });
  }

  onunload() {
    this.started = false;
    if (this.inboxEventTimer !== null) {
      window.clearTimeout(this.inboxEventTimer);
      this.inboxEventTimer = null;
    }
    if (this.controlSaveTimer !== null) {
      window.clearTimeout(this.controlSaveTimer);
      this.controlSaveTimer = null;
    }
    this.app.workspace.detachLeavesOfType?.(CONTROL_VIEW_TYPE);
    this.updateStatus(text("PaperFlow 自动化：已停止", "PaperFlow automation: stopped"));
  }

  async saveSettings() {
    await this.saveData(this.settings);
  }

  scheduleControlSettingsSave() {
    if (this.controlSaveTimer !== null) {
      window.clearTimeout(this.controlSaveTimer);
    }
    this.controlSaveTimer = window.setTimeout(() => {
      this.controlSaveTimer = null;
      void this.saveSettings();
    }, 250);
  }

  async activateControlCenter() {
    const workspace = this.app.workspace;
    let leaf = workspace.getLeavesOfType(CONTROL_VIEW_TYPE)[0];
    if (!leaf) {
      leaf = workspace.getRightLeaf(false);
      if (!leaf) throw new Error("无法创建 PaperFlow 控制中心视图。");
      await leaf.setViewState({
        type: CONTROL_VIEW_TYPE,
        active: true
      });
    }
    workspace.revealLeaf(leaf);
  }

  refreshControlCenter() {
    for (const leaf of this.app.workspace.getLeavesOfType?.(CONTROL_VIEW_TYPE) || []) {
      leaf.view?.updateRuntime?.();
    }
  }

  vaultRoot() {
    const adapter = this.app.vault.adapter;
    if (!Platform.isDesktopApp || typeof adapter.getBasePath !== "function") {
      throw new Error(text("PaperFlow 自动化仅支持 Obsidian 桌面版。", "PaperFlow automation requires Obsidian Desktop."));
    }
    return path.resolve(adapter.getBasePath());
  }

  updateStatus(message) {
    this.settings.runtime.lastMessage = message;
    if (this.statusBar) {
      this.statusBar.setText(message);
      this.statusBar.setAttr("aria-label", message);
    }
  }

  statusSummary() {
    const runtime = this.settings.runtime;
    return [
      text("PaperFlow 自动化", "PaperFlow automation"),
      `${text("状态", "Status")}: ${this.settings.enabled ? text("已启用", "enabled") : text("已停用", "disabled")}`,
      `${text("当前作业", "Running")}: ${this.runningJob || text("无", "none")}`,
      `${text("每日时间", "Daily time")}: ${this.settings.dailyLocalTime} Asia/Shanghai`,
      `${text("Inbox 间隔", "Inbox interval")}: ${this.settings.inboxIntervalMinutes} min`,
      `${text("最近每日运行", "Last daily")}: ${runtime.lastDailyAt || "-"}`,
      `${text("最近 Inbox 运行", "Last Inbox")}: ${runtime.lastInboxAt || "-"}`,
      `${text("最近订阅同步", "Last source sync")}: ${runtime.lastSourceSyncAt || "-"}`,
      `${text("最近自动发布", "Last auto publish")}: ${runtime.lastPublishAt || "-"}`,
      `${text("最近更新检查", "Last update check")}: ${runtime.lastUpdateCheckAt || "-"}`,
      `${text("最近消息", "Last message")}: ${runtime.lastMessage || "-"}`
    ].join("\n");
  }

  async startAutomation() {
    if (this.started) return;
    this.started = true;
    if (!Platform.isDesktopApp) {
      this.updateStatus(text("PaperFlow 自动化：桌面版限定", "PaperFlow automation: desktop only"));
      return;
    }
    if (!this.settings.enabled) {
      this.updateStatus(text("PaperFlow 自动化：已停用", "PaperFlow automation: disabled"));
      return;
    }
    await this.writeLocaleMarker();

    try {
      parseLocalTime(this.settings.dailyLocalTime);
    } catch (error) {
      const message = text(
        `PaperFlow 自动化：配置错误：${error.message}`,
        `PaperFlow automation: configuration error: ${error.message}`
      );
      this.updateStatus(message);
      new Notice(message, 12000);
      return;
    }
    const intervalMinutes = Math.max(1, Number(this.settings.inboxIntervalMinutes) || 5);
    this.registerEvent(
      this.app.vault.on("create", (file) => this.onVaultFileEvent(file))
    );
    this.registerEvent(
      this.app.vault.on("modify", (file) => this.onVaultFileEvent(file))
    );
    this.registerEvent(
      this.app.vault.on("rename", (file) => this.onVaultFileEvent(file))
    );
    this.registerInterval(
      window.setInterval(() => void this.runJob("inbox", "interval"), intervalMinutes * 60 * 1000)
    );
    this.registerInterval(
      window.setInterval(() => void this.checkAutomationTracks(), 60 * 1000)
    );

    await this.checkAutomationTracks();
    const startupTimer = window.setTimeout(() => void this.runJob("inbox", "startup"), 5000);
    this.register(() => window.clearTimeout(startupTimer));
    this.updateStatus(text("PaperFlow 自动化：已启用", "PaperFlow automation: enabled"));
    await this.saveSettings();
  }

  onVaultFileEvent(file) {
    if (!isInboxRequestPath(file?.path)) {
      return;
    }
    if (this.inboxEventTimer !== null) {
      window.clearTimeout(this.inboxEventTimer);
    }
    const delay = Math.max(250, Number(this.settings.inboxEventDebounceMs) || 1500);
    this.inboxEventTimer = window.setTimeout(() => {
      this.inboxEventTimer = null;
      void this.runJob("inbox", "vault-event");
    }, delay);
  }

  async writeLocaleMarker() {
    const root = this.vaultRoot();
    const state = path.resolve(root, ".paperflow", "state");
    const marker = path.resolve(state, "obsidian-locale.json");
    const relative = path.relative(root, marker);
    if (relative.startsWith("..") || path.isAbsolute(relative)) {
      throw new Error("Obsidian locale marker escaped the Vault");
    }
    await fs.promises.mkdir(state, { recursive: true });
    await fs.promises.writeFile(
      marker,
      JSON.stringify({
        locale: isChinese() ? "zh-CN" : "en",
        source: "obsidian",
        updated_at: new Date().toISOString()
      }, null, 2) + "\n",
      "utf8"
    );
  }

  async checkDaily() {
    if (!this.settings.enabled || this.runningJob) return false;
    const result = shouldRunDaily(this.settings);
    if (result.due) {
      await this.runJob("daily", "catch-up");
      return true;
    }
    return false;
  }

  async checkAutomationTracks() {
    if (!this.settings.enabled || this.runningJob) return;
    if (await this.checkDaily()) return;
    const runtime = this.settings.runtime;
    if (
      this.settings.sourceSyncEnabled &&
      intervalDue(
        runtime.lastSourceSyncAt,
        this.settings.sourceSyncIntervalMinutes
      )
    ) {
      await this.runJob("source-sync", "schedule");
      return;
    }
    if (
      this.settings.autoPublishEnabled &&
      intervalDue(
        runtime.lastPublishAt,
        this.settings.autoPublishIntervalMinutes
      )
    ) {
      await this.runJob("publish-auto", "schedule");
      return;
    }
    if (
      this.settings.updateCheckEnabled &&
      intervalDue(
        runtime.lastUpdateCheckAt,
        this.settings.updateCheckIntervalMinutes
      )
    ) {
      await this.runJob("update-auto", "schedule");
    }
  }

  async runJob(kind, trigger) {
    if (!this.settings.enabled) {
      if (trigger === "manual") new Notice(text("PaperFlow 自动化当前已停用。", "PaperFlow automation is disabled."));
      return;
    }
    if (this.runningJob) {
      this.updateStatus(text(`PaperFlow：${this.runningJob} 运行中，跳过 ${kind}`, `PaperFlow: ${this.runningJob} running; skipped ${kind}`));
      return;
    }

    const root = this.vaultRoot();
    const vaultPython = path.resolve(root, this.settings.pythonRelativePath);
    const relativePython = path.relative(root, vaultPython);
    const validVaultPython =
      !relativePython.startsWith("..") &&
      !path.isAbsolute(relativePython) &&
      fs.existsSync(vaultPython);
    const python =
      this.settings.preferVaultPython && validVaultPython
        ? vaultPython
        : String(this.settings.pythonExecutable || "python");
    const runtimeSource = path.resolve(root, ".paperflow", "src");
    const source = fs.existsSync(runtimeSource)
      ? runtimeSource
      : path.resolve(root, "src");

    this.runningJob = kind;
    this.updateStatus(text(`PaperFlow：正在运行 ${kind}`, `PaperFlow: running ${kind}`));
    await this.saveSettings();
    const started = Date.now();

    try {
      const result = await this.spawnPaperFlow(python, source, root, jobArguments(kind));
      const now = new Date();
      const clock = beijingClock(now);
      const timestamp = now.toISOString();
      if (kind === "daily") {
        this.settings.runtime.lastDailyDate = clock.date;
        this.settings.runtime.lastDailyAt = timestamp;
        this.settings.runtime.lastDailyExitCode = result.code;
      } else if (kind === "inbox") {
        this.settings.runtime.lastInboxAt = timestamp;
        this.settings.runtime.lastInboxExitCode = result.code;
      } else if (kind === "source-sync") {
        this.settings.runtime.lastSourceSyncAt = timestamp;
        this.settings.runtime.lastSourceSyncExitCode = result.code;
      } else if (kind === "publish-auto") {
        this.settings.runtime.lastPublishAt = timestamp;
        this.settings.runtime.lastPublishExitCode = result.code;
      } else if (kind === "update-auto") {
        this.settings.runtime.lastUpdateCheckAt = timestamp;
        this.settings.runtime.lastUpdateCheckExitCode = result.code;
        if (result.code === 0) {
          try {
            const update = JSON.parse(result.stdout);
            if (update.update_available) {
              this.settings.runtime.updateAvailableVersion =
                String(update.latest_version || "");
              new Notice(
                text(
                  `PaperFlow ${update.latest_version} 已发现并安全暂存；请在控制中心确认升级。`,
                  `PaperFlow ${update.latest_version} was found and safely staged; confirm the upgrade in Control Center.`
                ),
                15000
              );
            }
          } catch {
            // Keep the raw output available without trusting non-JSON text.
          }
        }
      }
      const elapsed = ((Date.now() - started) / 1000).toFixed(1);
      const message = result.code === 0
        ? text(`PaperFlow：${kind} 完成（${elapsed}s）`, `PaperFlow: ${kind} completed (${elapsed}s)`)
        : text(`PaperFlow：${kind} 失败，退出码 ${result.code}`, `PaperFlow: ${kind} failed with exit code ${result.code}`);
      this.updateStatus(message);
      if (
        result.code !== 0 ||
        trigger === "manual" ||
        (trigger === "schedule" && kind === "publish-auto" && result.code !== 0)
      ) {
        const detail = (result.stderr || result.stdout || "").trim().slice(-1000);
        new Notice(detail ? `${message}\n${detail}` : message, 12000);
      }
    } catch (error) {
      const message = text(`PaperFlow：${kind} 启动失败：${error.message}`, `PaperFlow: failed to start ${kind}: ${error.message}`);
      this.updateStatus(message);
      if (trigger === "manual") new Notice(message, 12000);
    } finally {
      this.runningJob = null;
      await this.saveSettings();
    }
  }

  async runControlAction(action, payload = {}) {
    let commands;
    try {
      commands = controlCommands(action, payload);
    } catch (error) {
      const message = text(
        `PaperFlow：${error.message}`,
        `PaperFlow: ${error.message}`
      );
      new Notice(message, 10000);
      throw error;
    }
    if (this.runningJob) {
      const message = text(
        `PaperFlow：${this.runningJob} 运行中，请稍后再试。`,
        `PaperFlow: ${this.runningJob} is running; try again later.`
      );
      new Notice(message, 8000);
      return { code: 75, stdout: "", stderr: message };
    }
    const root = this.vaultRoot();
    const vaultPython = path.resolve(root, this.settings.pythonRelativePath);
    const relativePython = path.relative(root, vaultPython);
    const validVaultPython =
      !relativePython.startsWith("..") &&
      !path.isAbsolute(relativePython) &&
      fs.existsSync(vaultPython);
    const python =
      this.settings.preferVaultPython && validVaultPython
        ? vaultPython
        : String(this.settings.pythonExecutable || "python");
    const runtimeSource = path.resolve(root, ".paperflow", "src");
    const source = fs.existsSync(runtimeSource)
      ? runtimeSource
      : path.resolve(root, "src");
    const started = Date.now();
    const output = [];
    let result = { code: 0, stdout: "", stderr: "" };

    this.runningJob = action;
    this.updateStatus(text(`PaperFlow：正在执行 ${action}`, `PaperFlow: running ${action}`));
    this.refreshControlCenter();
    try {
      for (const argumentsList of commands) {
        output.push(`$ paperflow ${argumentsList.join(" ")}`);
        result = await this.spawnPaperFlow(
          python,
          source,
          root,
          ["-m", "paperflow.cli", ...argumentsList]
        );
        const detail = (result.stdout || result.stderr || "").trim();
        if (detail) output.push(detail);
        if (result.code !== 0) break;
      }
      const elapsed = ((Date.now() - started) / 1000).toFixed(1);
      this.settings.runtime.lastControlAt = new Date().toISOString();
      this.settings.runtime.lastControlAction = action;
      this.settings.runtime.lastControlExitCode = result.code;
      this.settings.runtime.lastControlOutput = output.join("\n\n").slice(-16000);
      const message = result.code === 0
        ? text(`PaperFlow：${action} 完成（${elapsed}s）`, `PaperFlow: ${action} completed (${elapsed}s)`)
        : text(`PaperFlow：${action} 失败，退出码 ${result.code}`, `PaperFlow: ${action} failed with exit code ${result.code}`);
      this.updateStatus(message);
      new Notice(message, result.code === 0 ? 5000 : 12000);
      return result;
    } catch (error) {
      const message = text(
        `PaperFlow：${action} 启动失败：${error.message}`,
        `PaperFlow: ${action} failed to start: ${error.message}`
      );
      this.settings.runtime.lastControlAt = new Date().toISOString();
      this.settings.runtime.lastControlAction = action;
      this.settings.runtime.lastControlExitCode = -1;
      this.settings.runtime.lastControlOutput = message;
      this.updateStatus(message);
      new Notice(message, 12000);
      return { code: -1, stdout: "", stderr: message };
    } finally {
      this.runningJob = null;
      await this.saveSettings();
      this.refreshControlCenter();
    }
  }

  spawnPaperFlow(python, source, root, args) {
    return new Promise((resolve, reject) => {
      const child = spawn(python, args, {
        cwd: root,
        shell: false,
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
        env: {
          ...process.env,
          PAPERFLOW_VAULT: root,
          ...(fs.existsSync(source)
            ? {
                PYTHONPATH: process.env.PYTHONPATH
                  ? `${source}${path.delimiter}${process.env.PYTHONPATH}`
                  : source
              }
            : {}),
          PYTHONUTF8: "1"
        }
      });
      let stdout = "";
      let stderr = "";
      const append = (current, chunk) => (current + chunk.toString("utf8")).slice(-16000);
      child.stdout.on("data", (chunk) => { stdout = append(stdout, chunk); });
      child.stderr.on("data", (chunk) => { stderr = append(stderr, chunk); });
      child.once("error", reject);
      child.once("close", (code) => resolve({ code: Number(code ?? -1), stdout, stderr }));
    });
  }
}

class PaperFlowConfirmModal extends Modal {
  constructor(app, options) {
    super(app);
    this.options = options;
  }

  onOpen() {
    const { contentEl } = this;
    contentEl.addClass("paperflow-confirm-modal");
    contentEl.createEl("div", {
      cls: "paperflow-eyebrow",
      text: text("外部写入确认", "External write confirmation")
    });
    contentEl.createEl("h2", { text: this.options.title });
    contentEl.createEl("p", { text: this.options.body });
    const actions = contentEl.createDiv({ cls: "paperflow-modal-actions" });
    const cancel = actions.createEl("button", {
      text: text("取消", "Cancel")
    });
    cancel.addEventListener("click", () => this.close());
    const confirm = actions.createEl("button", {
      cls: "mod-warning",
      text: this.options.confirmLabel
    });
    confirm.addEventListener("click", () => {
      this.close();
      void this.options.onConfirm();
    });
  }

  onClose() {
    this.contentEl.empty();
  }
}

class PaperFlowControlCenterView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
    this.runtimeEls = {};
  }

  getViewType() {
    return CONTROL_VIEW_TYPE;
  }

  getDisplayText() {
    return text("PaperFlow 控制中心", "PaperFlow Control Center");
  }

  getIcon() {
    return "library-big";
  }

  async onOpen() {
    this.render();
  }

  control() {
    return this.plugin.settings.controlCenter;
  }

  persist(key, value) {
    this.control()[key] = value;
    this.plugin.scheduleControlSettingsSave();
  }

  section(parent, number, title, subtitle, tone = "") {
    const card = parent.createDiv({
      cls: `paperflow-card ${tone}`.trim()
    });
    const header = card.createDiv({ cls: "paperflow-card-header" });
    header.createEl("span", {
      cls: "paperflow-card-index",
      text: number
    });
    const copy = header.createDiv();
    copy.createEl("h3", { text: title });
    copy.createEl("p", { text: subtitle });
    return card.createDiv({ cls: "paperflow-card-body" });
  }

  label(parent, title, description = "") {
    const wrapper = parent.createDiv({ cls: "paperflow-field" });
    const label = wrapper.createEl("label");
    label.createEl("span", { text: title });
    if (description) {
      label.createEl("small", { text: description });
    }
    return { wrapper, label };
  }

  textInput(parent, key, title, placeholder, options = {}) {
    const { wrapper, label } = this.label(
      parent,
      title,
      options.description || ""
    );
    const input = label.createEl("input");
    input.type = options.type || "text";
    input.placeholder = placeholder;
    input.value = String(this.control()[key] || "");
    input.autocomplete = "off";
    input.spellcheck = false;
    input.addEventListener("input", () => this.persist(key, input.value));
    return input;
  }

  selectInput(parent, key, title, options) {
    const { wrapper, label } = this.label(parent, title);
    const select = label.createEl("select");
    for (const [value, caption] of options) {
      const option = select.createEl("option", { text: caption });
      option.value = value;
    }
    select.value = String(this.control()[key]);
    select.addEventListener("change", () => this.persist(key, select.value));
    return select;
  }

  toggleInput(parent, key, title, description = "") {
    const row = parent.createEl("label", { cls: "paperflow-toggle-row" });
    const input = row.createEl("input");
    input.type = "checkbox";
    input.checked = Boolean(this.control()[key]);
    const copy = row.createDiv();
    copy.createEl("span", { text: title });
    if (description) copy.createEl("small", { text: description });
    input.addEventListener("change", () => this.persist(key, input.checked));
    return input;
  }

  button(parent, label, icon, action, payload = () => ({}), tone = "") {
    const button = parent.createEl("button", {
      cls: `paperflow-action ${tone}`.trim()
    });
    setIcon(button, icon);
    button.createSpan({ text: label });
    button.addEventListener("click", () => {
      if (action === "git-push" || action === "update-apply") {
        const update = action === "update-apply";
        new PaperFlowConfirmModal(this.app, {
          title: update
            ? text("应用已验证的 PaperFlow 更新？", "Apply the verified PaperFlow update?")
            : text("推送公共 Feed？", "Push the public Feed?"),
          body: text(
            update
              ? "PaperFlow 将先创建 Workspace 备份，再替换已暂存且 SHA256 验证通过的程序运行时，迁移 Workspace 并升级 Obsidian 插件。失败会恢复旧运行时；成功后需要重启 Obsidian。"
              : "PaperFlow 将再次验证 Feed 和隐私扫描，然后把本地 Feed 分支推送到 origin。此操作不会上传用户数据或 PDF，但会修改远程 GitHub 仓库。",
            update
              ? "PaperFlow will back up the Workspace, replace the staged SHA256-verified runtime, migrate the Workspace, and upgrade the Obsidian plugin. A failed finalization restores the previous runtime; success requires an Obsidian restart."
              : "PaperFlow will validate and privacy-scan the Feed again, then push its local branch to origin. This changes the remote GitHub repository."
          ),
          confirmLabel: update
            ? text("确认安全升级", "Confirm safe upgrade")
            : text("确认推送", "Confirm push"),
          onConfirm: () => this.plugin.runControlAction(action, payload())
        }).open();
        return;
      }
      if (action === "source-remove") {
        new PaperFlowConfirmModal(this.app, {
          title: text("移除这个订阅？", "Remove this subscription?"),
          body: text(
            "只移除本地订阅配置；已同步的不可变记录和用户数据保持不变。",
            "Only the local subscription configuration is removed. Synced immutable records and User Data remain."
          ),
          confirmLabel: text("确认移除", "Confirm removal"),
          onConfirm: () => this.plugin.runControlAction(action, payload())
        }).open();
        return;
      }
      void this.plugin.runControlAction(action, payload());
    });
    return button;
  }

  vaultButton(parent, label, icon, target, tone = "") {
    const button = parent.createEl("button", {
      cls: `paperflow-action ${tone}`.trim()
    });
    setIcon(button, icon);
    button.createSpan({ text: label });
    button.addEventListener("click", async () => {
      try {
        await this.app.workspace.openLinkText(target, "", true);
      } catch (error) {
        new Notice(
          text(
            `无法打开 ${label}：${error.message}`,
            `Could not open ${label}: ${error.message}`
          )
        );
      }
    });
    return button;
  }

  buttonRow(parent) {
    return parent.createDiv({ cls: "paperflow-action-row" });
  }

  automationToggle(parent, key, title, description = "", options = {}) {
    const row = parent.createEl("label", { cls: "paperflow-automation-toggle" });
    const input = row.createEl("input");
    input.type = "checkbox";
    input.checked = Boolean(this.plugin.settings[key]);
    const copy = row.createDiv();
    copy.createEl("strong", { text: title });
    if (description) copy.createEl("small", { text: description });
    input.addEventListener("change", async () => {
      if (input.checked && options.confirmPublish) {
        input.checked = false;
        new PaperFlowConfirmModal(this.app, {
          title: text("启用无人值守公共发布？", "Enable unattended public publishing?"),
          body: text(
            "启用后，PaperFlow 会按固定间隔构建 Feed；只有验证、隐私扫描、固定 origin 和分支全部通过且内容确有变化时，才自动 commit 并 push。关闭开关可随时停止。",
            "PaperFlow will build the Feed on schedule. It commits and pushes only when validation, privacy scanning, the fixed origin/branch, and a real content change all pass. Turn this off at any time."
          ),
          confirmLabel: text("授权自动发布", "Authorize auto publishing"),
          onConfirm: async () => {
            this.plugin.settings[key] = true;
            await this.plugin.saveSettings();
            this.render();
          }
        }).open();
        return;
      }
      this.plugin.settings[key] = input.checked;
      await this.plugin.saveSettings();
      this.render();
    });
    return input;
  }

  automationNumber(parent, key, title, minimum = 5) {
    const label = parent.createEl("label", { cls: "paperflow-automation-number" });
    label.createEl("span", { text: title });
    const input = label.createEl("input");
    input.type = "number";
    input.min = String(minimum);
    input.value = String(this.plugin.settings[key]);
    input.addEventListener("change", async () => {
      const value = Math.max(minimum, Math.trunc(Number(input.value) || minimum));
      input.value = String(value);
      this.plugin.settings[key] = value;
      await this.plugin.saveSettings();
    });
    return input;
  }

  renderAutomationOrchestrator(container) {
    const header = container.createDiv({ cls: "paperflow-section-heading paperflow-automation-heading" });
    header.createEl("span", { text: text("OBSIDIAN 内部自动化", "OBSIDIAN-NATIVE AUTOMATION") });
    header.createEl("h2", { text: text("三条自动化轨道", "Three automation tracks") });
    const grid = container.createDiv({ cls: "paperflow-automation-grid" });

    const source = grid.createDiv({ cls: "paperflow-automation-track is-source" });
    source.createEl("span", { cls: "paperflow-track-index", text: "01 / SYNC" });
    source.createEl("h3", { text: text("指定订阅同步", "Selected source sync") });
    source.createEl("p", {
      text: text(
        "按间隔同步所有已启用订阅；在订阅管理中可逐源启用、禁用和设置信任级别。",
        "Sync all enabled sources on schedule; enable, disable, and set trust per source in subscription management."
      )
    });
    this.automationToggle(
      source,
      "sourceSyncEnabled",
      text("自动同步已启用订阅", "Automatically sync enabled sources")
    );
    this.automationNumber(
      source,
      "sourceSyncIntervalMinutes",
      text("间隔（分钟）", "Interval (minutes)")
    );
    const sourceActions = this.buttonRow(source);
    const sourceNow = sourceActions.createEl("button", { cls: "paperflow-action" });
    setIcon(sourceNow, "refresh-cw");
    sourceNow.createSpan({ text: text("立即同步", "Sync now") });
    sourceNow.addEventListener("click", () => void this.plugin.runJob("source-sync", "manual"));
    source.createEl("small", {
      cls: "paperflow-track-status",
      text: `${text("最近", "Last")}: ${this.plugin.settings.runtime.lastSourceSyncAt || "—"}`
    });

    const publish = grid.createDiv({ cls: "paperflow-automation-track is-publish" });
    publish.createEl("span", { cls: "paperflow-track-index", text: "02 / PUBLISH" });
    publish.createEl("h3", { text: text("数据源自动发布", "Automatic source publishing") });
    publish.createEl("p", {
      text: text(
        "只向固定 PaperRead origin 发布；无变化不提交，任一安全门失败即停止。",
        "Publish only to the fixed PaperRead origin; no change means no commit, and any failed safety gate stops the run."
      )
    });
    this.automationToggle(
      publish,
      "autoPublishEnabled",
      text("授权自动构建并 Push", "Authorize automatic build and push"),
      "",
      { confirmPublish: true }
    );
    this.automationNumber(
      publish,
      "autoPublishIntervalMinutes",
      text("间隔（分钟）", "Interval (minutes)")
    );
    const publishActions = this.buttonRow(publish);
    const publishNow = publishActions.createEl("button", { cls: "paperflow-action" });
    setIcon(publishNow, "cloud-upload");
    publishNow.createSpan({ text: text("安全发布一次", "Run safe publish") });
    publishNow.addEventListener("click", () => {
      new PaperFlowConfirmModal(this.app, {
        title: text("执行一次安全发布？", "Run one safe publication?"),
        body: text(
          "将执行构建、验证、隐私扫描、差异检查，并在有变化时 commit/push 固定远端。",
          "Build, validation, privacy scan, and diff checks will run; changes are committed and pushed only to the fixed remote."
        ),
        confirmLabel: text("确认发布", "Confirm publish"),
        onConfirm: () => this.plugin.runJob("publish-auto", "manual")
      }).open();
    });
    publish.createEl("small", {
      cls: "paperflow-track-status",
      text: `${text("最近", "Last")}: ${this.plugin.settings.runtime.lastPublishAt || "—"}`
    });

    const update = grid.createDiv({ cls: "paperflow-automation-track is-update" });
    update.createEl("span", { cls: "paperflow-track-index", text: "03 / UPDATE" });
    update.createEl("h3", { text: text("发现并安全升级", "Discover and safely upgrade") });
    update.createEl("p", {
      text: text(
        "定时检查固定 GitHub Releases；可自动下载并校验，应用升级始终需要确认。",
        "Check the fixed GitHub Releases source; verified staging may be automatic, but applying an upgrade always requires confirmation."
      )
    });
    this.textInput(
      update,
      "updateRepository",
      text("版本发布仓库", "Release repository"),
      "https://github.com/owner/PaperFlow"
    );
    this.automationToggle(
      update,
      "updateCheckEnabled",
      text("自动检查并暂存", "Automatically check and stage")
    );
    this.toggleInput(
      update,
      "updateAutoStage",
      text("发现新版后自动下载并校验", "Automatically download and verify new releases")
    );
    this.automationNumber(
      update,
      "updateCheckIntervalMinutes",
      text("间隔（分钟）", "Interval (minutes)"),
      30
    );
    const updateActions = this.buttonRow(update);
    this.button(
      updateActions,
      text("保存更新源", "Save update source"),
      "save",
      "update-save",
      () => ({
        repository: this.control().updateRepository,
        autoCheck: this.plugin.settings.updateCheckEnabled,
        autoStage: this.control().updateAutoStage
      })
    );
    this.button(updateActions, text("检查", "Check"), "search-check", "update-check");
    this.button(updateActions, text("下载并校验", "Stage verified"), "package-down", "update-stage");
    this.button(updateActions, text("确认升级", "Apply update"), "circle-arrow-up", "update-apply", () => ({}), "primary");
    update.createEl("small", {
      cls: "paperflow-track-status",
      text: this.plugin.settings.runtime.updateAvailableVersion
        ? text(
            `可升级至 ${this.plugin.settings.runtime.updateAvailableVersion}`,
            `Update ${this.plugin.settings.runtime.updateAvailableVersion} is ready`
          )
        : `${text("最近检查", "Last check")}: ${this.plugin.settings.runtime.lastUpdateCheckAt || "—"}`
    });
  }

  taskEntry(parent, eyebrow, title, description, icon, options) {
    const entry = parent.createDiv({ cls: "paperflow-task-entry" });
    const heading = entry.createDiv({ cls: "paperflow-task-entry-heading" });
    const mark = heading.createDiv({ cls: "paperflow-task-entry-icon" });
    setIcon(mark, icon);
    const copy = heading.createDiv();
    copy.createEl("span", { text: eyebrow });
    copy.createEl("strong", { text: title });
    entry.createEl("p", { text: description });
    const actions = this.buttonRow(entry);
    if (options.target) {
      this.vaultButton(actions, options.label, options.actionIcon, options.target);
    } else {
      this.button(
        actions,
        options.label,
        options.actionIcon,
        options.action,
        options.payload || (() => ({}))
      );
    }
    return entry;
  }

  renderTaskShelf(container) {
    const shelf = container.createDiv({ cls: "paperflow-task-shelf" });
    this.taskEntry(
      shelf,
      text("收集", "COLLECT"),
      text("添加论文", "Add a paper"),
      text("从链接、DOI、PDF 或 arXiv ID 开始", "Start from a URL, DOI, PDF, or arXiv ID"),
      "plus-circle",
      {
        label: text("填写导入信息", "Enter paper details"),
        actionIcon: "arrow-up-right",
        target: "90 System/Forms/Add Paper"
      }
    );
    this.taskEntry(
      shelf,
      text("发现", "DISCOVER"),
      text("发现新论文", "Discover papers"),
      text("按已保存主题抓取新的候选论文", "Fetch new candidates from saved topics"),
      "radar",
      {
        label: text("开始发现", "Run discovery"),
        actionIcon: "play",
        action: "discover"
      }
    );
    this.taskEntry(
      shelf,
      text("资料库", "LIBRARY"),
      text("浏览论文库", "Browse the library"),
      text("筛选未读、高价值和最近导入论文", "Filter unread, high-value, and recent papers"),
      "library",
      {
        label: text("打开论文库", "Open library"),
        actionIcon: "arrow-up-right",
        target: "00 Dashboard/Bases/Paper Library.base"
      }
    );
    this.taskEntry(
      shelf,
      text("阅读", "READ"),
      text("继续阅读", "Continue reading"),
      text("查看待读项目并推进阅读状态", "Review queued papers and advance reading status"),
      "book-open",
      {
        label: text("打开阅读队列", "Open reading queue"),
        actionIcon: "arrow-up-right",
        target: "00 Dashboard/Bases/Reading Queue.base"
      }
    );
    this.taskEntry(
      shelf,
      text("复现", "REPRODUCE"),
      text("推进复现", "Reproduce results"),
      text("查看需要复现、验证或补充实验的论文", "Review papers needing reproduction or validation"),
      "flask-conical",
      {
        label: text("打开复现队列", "Open reproduction queue"),
        actionIcon: "arrow-up-right",
        target: "00 Dashboard/Bases/Reproduction Queue.base"
      }
    );
    this.taskEntry(
      shelf,
      text("回顾", "REVIEW"),
      text("每日研究回顾", "Daily research review"),
      text("处理 Inbox、生成简报并检查当日导入", "Process Inbox, build a brief, and inspect today's intake"),
      "calendar-check",
      {
        label: text("打开每日导入", "Open daily intake"),
        actionIcon: "arrow-up-right",
        target: "00 Dashboard/Bases/Daily Intake.base"
      }
    );
  }

  render() {
    const container = this.contentEl || this.containerEl;
    container.empty();
    container.addClass("paperflow-control-center");

    const hero = container.createDiv({ cls: "paperflow-control-hero" });
    const titleBlock = hero.createDiv();
    titleBlock.createEl("div", {
      cls: "paperflow-eyebrow",
      text: text("PAPERFLOW / 研究工作台", "PAPERFLOW / RESEARCH WORKSPACE")
    });
    titleBlock.createEl("h1", {
      text: text("今天想做什么？", "What would you like to do?")
    });
    titleBlock.createEl("p", {
      text: text(
        "从当前研究目标进入：收集、发现、阅读、分析、复现、回顾与 Agent 配置互相独立；工作台会随 PaperFlow 能力继续扩展。",
        "Enter from your current research goal. Collection, discovery, reading, analysis, reproduction, review, and Agent configuration are independent, and the workspace can grow with PaperFlow."
      )
    });
    const seal = hero.createDiv({ cls: "paperflow-hero-seal" });
    seal.createEl("span", { text: "PF" });
    seal.createEl("small", { text: "LOCAL FIRST" });

    const badges = container.createDiv({
      cls: "paperflow-badge-row paperflow-status-row"
    });
    for (const [label, value, tone] of [
      [text("自动化", "Automation"), this.plugin.settings.enabled ? "ON" : "OFF", "live"],
      [text("每日任务", "Daily run"), this.plugin.settings.dailyLocalTime, "safe"],
      [text("当前 Agent", "Active Agent"), this.control().aiProvider.toUpperCase(), "neutral"],
      [text("工具权限", "Tool access"), text("只读暂存区", "STAGED READ-ONLY"), "safe"]
    ]) {
      const badge = badges.createDiv({ cls: `paperflow-badge ${tone}` });
      badge.createEl("span", { text: label });
      badge.createEl("strong", { text: value });
    }

    this.renderAutomationOrchestrator(container);
    this.renderTaskShelf(container);

    const quick = container.createDiv({ cls: "paperflow-quick-strip" });
    quick.createEl("span", {
      cls: "paperflow-quick-label",
      text: text("立即执行", "RUN NOW")
    });
    this.button(quick, text("处理 Inbox", "Process Inbox"), "inbox", "inbox");
    this.button(quick, text("生成今日简报", "Run daily brief"), "calendar-clock", "daily");
    this.vaultButton(
      quick,
      text("导入请求", "Import requests"),
      "list-todo",
      "00 Dashboard/Bases/Paper Requests.base"
    );
    this.button(quick, text("运行状态", "Run status"), "activity", "status");

    const focusHeader = container.createDiv({ cls: "paperflow-section-heading" });
    focusHeader.createEl("span", { text: text("执行与配置", "EXECUTE & CONFIGURE") });
    focusHeader.createEl("h2", {
      text: text("需要输入的任务", "Tasks that need your input")
    });

    const grid = container.createDiv({
      cls: "paperflow-control-grid paperflow-primary-grid"
    });
    this.renderPaperCard(grid);
    this.renderAnalyzeCard(grid);
    this.renderAiCard(grid);
    this.renderActivityCard(grid);

    const advanced = container.createEl("details", {
      cls: "paperflow-advanced-tools"
    });
    const summary = advanced.createEl("summary");
    summary.createEl("span", { text: text("高级工具", "Advanced tools") });
    summary.createEl("small", {
      text: text(
        "Feed 订阅、公共发布、迁移与系统维护",
        "Feed subscriptions, publishing, migration, and maintenance"
      )
    });
    const advancedGrid = advanced.createDiv({
      cls: "paperflow-control-grid"
    });
    this.renderSubscriptionCard(advancedGrid);
    this.renderPublishCard(advancedGrid);
    this.renderMaintenanceCard(advancedGrid);
    this.updateRuntime();
  }

  renderPaperCard(grid) {
    const body = this.section(
      grid,
      text("论文入口", "PAPER INPUT"),
      text("添加 / 抓取论文", "Add or collect a paper"),
      text("粘贴 arXiv、DOI、PDF 或论文网页", "Paste an arXiv ID, DOI, PDF, or paper page"),
      "paperflow-card-accent"
    );
    this.textInput(
      body,
      "paperValue",
      text("论文链接或 ID", "Paper URL or ID"),
      "https://arxiv.org/abs/..."
    );
    const compact = body.createDiv({ cls: "paperflow-field-pair" });
    this.selectInput(compact, "paperPriority", text("优先级", "Priority"), [
      ["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"], ["5", "5"]
    ]);
    this.toggleInput(
      compact,
      "paperUseAi",
      text("立即进行 AI 分析", "Analyze with AI now")
    );
    const actions = this.buttonRow(body);
    this.button(
      actions,
      text("加入 PaperFlow", "Add to PaperFlow"),
      "plus",
      "paper-add",
      () => ({
        value: this.control().paperValue,
        priority: this.control().paperPriority,
        ai: this.control().paperUseAi
      }),
      "primary"
    );
  }

  renderAnalyzeCard(grid) {
    const body = this.section(
      grid,
      text("分析", "ANALYSIS"),
      text("分析已有论文", "Analyze an imported paper"),
      text(
        "输入 Paper UID；默认使用已保存的完整分析 Agent",
        "Enter a Paper UID; the saved full-analysis Agent is used by default"
      ),
      "paperflow-card-blue"
    );
    this.textInput(
      body,
      "analyzePaperUid",
      "Paper UID",
      "arxiv:2607.15275"
    );
    this.selectInput(
      body,
      "analyzeProvider",
      text("执行 Agent", "Execution Agent"),
      [
        ["configured", text("使用已保存设置", "Use saved settings")],
        ["codex", "Codex"],
        ["claude", "Claude Code"],
        ["mock", text("Mock（测试）", "Mock (test)")]
      ]
    );
    const actions = this.buttonRow(body);
    this.button(
      actions,
      text("开始分析", "Analyze paper"),
      "sparkles",
      "paper-analyze",
      () => ({
        paperUid: this.control().analyzePaperUid,
        provider: this.control().analyzeProvider
      }),
      "primary"
    );
    this.button(
      actions,
      text("查看运行状态", "Check status"),
      "activity",
      "status"
    );
  }

  renderAiCard(grid) {
    const body = this.section(
      grid,
      text("Agent", "AGENT"),
      text("设置执行 Agent", "Configure an execution Agent"),
      text(
        "配置用途、模型与推理强度；凭证保持不变",
        "Choose purpose, model, and reasoning effort; credentials remain untouched"
      )
    );
    const pair = body.createDiv({ cls: "paperflow-field-pair" });
    this.selectInput(pair, "aiProfile", "Profile", [
      ["triage", "Triage"],
      ["full_analysis", "Full analysis"],
      ["fallback_analysis", "Fallback"],
      ["reanalysis", "Reanalysis"]
    ]);
    this.selectInput(pair, "aiProvider", "Provider", [
      ["codex", "Codex"],
      ["claude", "Claude Code"],
      ["mock", "Mock"]
    ]);
    this.textInput(
      body,
      "aiModel",
      text("模型", "Model"),
      text("留空使用 CLI 默认模型", "Blank uses the CLI default")
    );
    this.selectInput(
      body,
      "aiReasoningEffort",
      text("Codex 推理强度", "Codex reasoning effort"),
      [
        ["", text("使用 CLI 默认值", "Use CLI default")],
        ["low", text("低", "Low")],
        ["medium", text("中", "Medium")],
        ["high", text("高", "High")],
        ["xhigh", text("极高", "Extra high")]
      ]
    );
    const tools = body.createDiv({ cls: "paperflow-agent-boundary" });
    tools.createEl("strong", {
      text: text("工具与数据边界", "Tool and data boundary")
    });
    tools.createEl("p", {
      text: text(
        "固定为只读暂存区。Codex 使用 read-only sandbox；Claude 禁用全部工具。Agent 不可写入 Vault，也不会运行论文或仓库中的脚本。",
        "Locked to staged read-only input. Codex uses a read-only sandbox; Claude has all tools disabled. Agents cannot write to the Vault or run paper/repository scripts."
      )
    });
    const policy = body.createDiv({ cls: "paperflow-field-pair" });
    this.textInput(
      policy,
      "aiTimeout",
      text("超时（秒）", "Timeout (seconds)"),
      "1800",
      { type: "number" }
    );
    this.selectInput(
      policy,
      "aiReanalyzeWhen",
      text("重新分析条件", "Reanalyze when"),
      [
        ["identity-changed", text("身份变化", "Identity changed")],
        ["never", text("从不", "Never")],
        ["always", text("总是", "Always")]
      ]
    );
    this.toggleInput(
      body,
      "aiFallback",
      text("允许 fallback", "Allow fallback"),
      text("失败时转到 fallback_analysis", "Use fallback_analysis after failure")
    );
    this.toggleInput(
      body,
      "aiReuseFeed",
      text("复用订阅 Feed 分析", "Reuse subscribed Feed analysis")
    );
    const actions = this.buttonRow(body);
    this.button(
      actions,
      text("保存 Agent 设置", "Save Agent settings"),
      "save",
      "ai-save",
      () => ({
        profile: this.control().aiProfile,
        provider: this.control().aiProvider,
        model: this.control().aiModel,
        timeout: this.control().aiTimeout,
        reasoningEffort: this.control().aiReasoningEffort,
        fallback: this.control().aiFallback,
        reuseFeed: this.control().aiReuseFeed,
        reanalyzeWhen: this.control().aiReanalyzeWhen
      }),
      "primary"
    );
    this.button(
      actions,
      text("测试配置", "Test profile"),
      "flask-conical",
      "ai-test",
      () => ({ profile: this.control().aiProfile })
    );
    this.button(actions, text("探测 Provider", "Probe providers"), "scan-search", "ai-providers");
  }

  renderSubscriptionCard(grid) {
    const body = this.section(
      grid,
      "03",
      text("GitHub Feed 订阅", "GitHub Feed subscriptions"),
      text("远程只读、禁用 Git hooks、校验 Schema 与哈希", "Read-only remote data with hooks, schema, and hashes controlled"),
      "paperflow-card-blue"
    );
    this.textInput(
      body,
      "sourceUrl",
      "GitHub URL",
      "https://github.com/owner/paperflow-feed"
    );
    this.textInput(
      body,
      "sourceName",
      text("本地订阅名称", "Local source name"),
      "community-feed"
    );
    this.selectInput(
      body,
      "sourceTrust",
      text("信任级别", "Trust level"),
      [
        ["metadata-and-ai", text("元数据与 AI", "Metadata and AI")],
        ["metadata-only", text("仅元数据", "Metadata only")],
        ["disabled", text("禁用", "Disabled")]
      ]
    );
    const actions = this.buttonRow(body);
    this.button(
      actions,
      text("添加订阅", "Add source"),
      "rss",
      "source-add",
      () => ({ url: this.control().sourceUrl, name: this.control().sourceName }),
      "primary"
    );
    this.button(
      actions,
      text("检查 Feed", "Inspect Feed"),
      "shield-check",
      "source-inspect",
      () => ({ name: this.control().sourceName })
    );
    this.button(
      actions,
      text("同步此源", "Sync source"),
      "refresh-cw",
      "source-sync",
      () => ({ name: this.control().sourceName })
    );
    this.button(actions, text("同步全部", "Sync all"), "refresh-ccw", "source-sync-all");
    this.button(
      actions,
      text("应用信任级别", "Apply trust"),
      "shield",
      "source-trust",
      () => ({
        name: this.control().sourceName,
        mode: this.control().sourceTrust
      })
    );
    this.button(
      actions,
      text("禁用", "Disable"),
      "pause",
      "source-disable",
      () => ({ name: this.control().sourceName })
    );
    this.button(
      actions,
      text("移除", "Remove"),
      "trash-2",
      "source-remove",
      () => ({ name: this.control().sourceName }),
      "danger"
    );
    this.button(actions, text("列出订阅", "List sources"), "list-tree", "source-list");
    this.button(actions, text("订阅状态", "Source status"), "radio-tower", "source-status");
  }

  renderPublishCard(grid) {
    const body = this.section(
      grid,
      "04",
      text("发布与 Git", "Publish & Git"),
      text("构建 → 验证 → 隐私扫描 → 提交 → 明确确认后推送", "Build → validate → privacy scan → commit → confirmed push"),
      "paperflow-card-dark"
    );
    body.createEl("div", {
      cls: "paperflow-caution",
      text: text(
        "许可证、feed_id 与发布者信息未配置时，构建会被后端阻止。",
        "The backend blocks builds until licensing, feed_id, and publisher metadata are configured."
      )
    });
    const identity = body.createDiv({ cls: "paperflow-field-pair" });
    this.textInput(
      identity,
      "publishFeedId",
      "Feed ID",
      "robotics-reading-feed"
    );
    this.textInput(
      identity,
      "publishName",
      text("Feed 名称", "Feed name"),
      "Robotics Reading Feed"
    );
    const publisher = body.createDiv({ cls: "paperflow-field-pair" });
    this.textInput(
      publisher,
      "publisherName",
      text("发布者名称", "Publisher name"),
      text("个人或组织名称", "Person or organization")
    );
    this.textInput(
      publisher,
      "publisherUrl",
      text("发布者 HTTPS URL（可空）", "Publisher HTTPS URL (optional)"),
      "https://example.org"
    );
    const policy = body.createDiv({ cls: "paperflow-field-pair" });
    this.textInput(
      policy,
      "dataLicense",
      text("数据许可证（由你决定）", "Data licence (your decision)"),
      "SPDX-or-custom-licence-id",
      {
        description: text(
          "PaperFlow 不会替你选择许可证。",
          "PaperFlow does not choose a licence for you."
        )
      }
    );
    this.textInput(
      policy,
      "publishBranch",
      text("Git 分支", "Git branch"),
      "main"
    );
    this.textInput(
      body,
      "publishRemote",
      text("公共 Feed GitHub 仓库", "Public Feed GitHub repository"),
      "https://github.com/owner/paperflow-feed"
    );
    this.textInput(
      body,
      "commitMessage",
      text("提交说明", "Commit message"),
      "Update PaperFlow Feed"
    );
    const prepare = this.buttonRow(body);
    this.button(
      prepare,
      text("保存发布配置", "Save publishing config"),
      "save",
      "publish-configure",
      () => ({
        feedId: this.control().publishFeedId,
        name: this.control().publishName,
        publisherName: this.control().publisherName,
        publisherUrl: this.control().publisherUrl,
        dataLicense: this.control().dataLicense,
        branch: this.control().publishBranch,
        remote: this.control().publishRemote
      }),
      "primary"
    );
    this.button(prepare, text("发布计划", "Plan"), "list-todo", "publish-plan");
    this.button(prepare, text("构建 Feed", "Build Feed"), "package-plus", "publish-build");
    this.button(prepare, text("验证", "Validate"), "badge-check", "publish-validate");
    this.button(prepare, text("隐私扫描", "Privacy scan"), "shield-alert", "publish-scan");
    this.button(prepare, text("本地快照", "Local snapshot"), "package-check", "publish-snapshot");
    const git = this.buttonRow(body);
    this.button(
      git,
      text("初始化 Git", "Initialize Git"),
      "git-branch",
      "git-init",
      () => ({ remote: this.control().publishRemote })
    );
    this.button(git, "Git status", "git-compare-arrows", "git-status");
    this.button(
      git,
      text("提交", "Commit"),
      "git-commit-horizontal",
      "git-commit",
      () => ({ message: this.control().commitMessage })
    );
    this.button(
      git,
      text("上传 / Push", "Upload / Push"),
      "cloud-upload",
      "git-push",
      () => ({}),
      "danger"
    );
  }

  renderMaintenanceCard(grid) {
    const body = this.section(
      grid,
      "05",
      text("维护与安全", "Maintenance & safety"),
      text("备份、迁移验证与只读预览", "Backup, migration verification, and read-only previews")
    );
    const actions = this.buttonRow(body);
    this.button(actions, text("Workspace 备份", "Workspace backup"), "archive", "workspace-backup");
    this.button(actions, "Workspace info", "info", "workspace-info");
    this.button(actions, text("验证 Workspace", "Validate workspace"), "badge-check", "workspace-validate");
    this.button(actions, text("修复预览", "Repair preview"), "wrench", "workspace-repair-preview");
    this.button(actions, text("迁移状态", "Migration status"), "route", "migrate-status");
    this.button(actions, text("迁移计划", "Migration plan"), "map", "migrate-plan");
    this.button(actions, text("验证迁移", "Verify migration"), "list-checks", "migrate-verify");
    this.button(actions, text("验证路径", "Validate paths"), "folder-check", "paths-validate");
    this.button(actions, text("路径预览", "Path preview"), "folders", "paths-preview");
    this.button(actions, text("渲染预览", "Render preview"), "eye", "render-preview");
    this.button(actions, text("全量验证", "Validate all"), "shield-check", "validate-all");
    this.button(actions, text("重试失败", "Retry failed"), "rotate-ccw", "retry-failed");
    this.button(actions, text("重建索引", "Rebuild index"), "database", "rebuild-index");
    this.button(actions, text("重建 Bases", "Rebuild Bases"), "table-properties", "rebuild-bases");
    this.button(actions, text("验证配置", "Validate config"), "file-check-2", "config-validate");
    this.button(actions, text("查看配置", "Show config"), "settings-2", "config-show");
    this.button(actions, "Form Flow status", "file-check", "form-flow-status");
    this.button(actions, text("检查更新", "Check updates"), "circle-arrow-up", "update-check");
  }

  renderActivityCard(grid) {
    const body = this.section(
      grid,
      "06",
      text("运行记录", "Activity"),
      text("仅保留最近 16 KB 输出；不保存凭证", "Only the latest 16 KB is retained; credentials are never stored"),
      "paperflow-card-output"
    );
    const meta = body.createDiv({ cls: "paperflow-runtime-meta" });
    this.runtimeEls.action = meta.createEl("strong");
    this.runtimeEls.time = meta.createEl("span");
    this.runtimeEls.exit = meta.createEl("span");
    this.runtimeEls.output = body.createEl("pre", {
      cls: "paperflow-output"
    });
  }

  updateRuntime() {
    if (!this.runtimeEls.output) return;
    const runtime = this.plugin.settings.runtime;
    const running = this.plugin.runningJob;
    this.runtimeEls.action.setText(
      running
        ? text(`运行中：${running}`, `Running: ${running}`)
        : runtime.lastControlAction || text("尚无控制中心操作", "No Control Center action yet")
    );
    this.runtimeEls.time.setText(runtime.lastControlAt || "—");
    const code = runtime.lastControlExitCode;
    this.runtimeEls.exit.setText(
      code === null || code === undefined ? "—" : `exit ${code}`
    );
    this.runtimeEls.exit.toggleClass("is-error", Number(code) !== 0 && code !== null);
    this.runtimeEls.output.setText(
      runtime.lastControlOutput ||
      text("操作输出将在这里显示。", "Command output will appear here.")
    );
  }
}

class PaperFlowAutomationSettingTab extends PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display() {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: text("PaperFlow 自动化", "PaperFlow Automation") });
    containerEl.createEl("p", {
      text: text(
        "调度由 Obsidian 插件生命周期驱动。Obsidian 关闭时不会运行；错过每日时间会在下次打开后补跑。",
        "Scheduling is driven by the Obsidian plugin lifecycle. Nothing runs while Obsidian is closed; missed daily work catches up after the next launch."
      )
    });

    new Setting(containerEl)
      .setName(text("PaperFlow 控制中心", "PaperFlow Control Center"))
      .setDesc(
        text(
          "在 Obsidian 内配置 AI、导入论文、同步 GitHub Feed 并执行受控发布。",
          "Configure AI, import papers, sync GitHub Feeds, and run controlled publishing inside Obsidian."
        )
      )
      .addButton((button) => button
        .setButtonText(text("打开控制中心", "Open Control Center"))
        .setCta()
        .onClick(() => void this.plugin.activateControlCenter()));

    new Setting(containerEl)
      .setName(text("启动时打开控制中心", "Open Control Center on startup"))
      .setDesc(
        text(
          "Obsidian 完成工作区加载后自动显示 PaperFlow 界面。",
          "Automatically show PaperFlow after the Obsidian workspace is ready."
        )
      )
      .addToggle((toggle) => toggle
        .setValue(this.plugin.settings.openControlCenterOnStartup)
        .onChange(async (value) => {
          this.plugin.settings.openControlCenterOnStartup = value;
          await this.plugin.saveSettings();
        }));

    new Setting(containerEl)
      .setName(text("启用自动化", "Enable automation"))
      .addToggle((toggle) => toggle
        .setValue(this.plugin.settings.enabled)
        .onChange(async (value) => {
          this.plugin.settings.enabled = value;
          await this.plugin.saveSettings();
          new Notice(text("请重新加载插件使调度变更生效。", "Reload the plugin to apply scheduling changes."));
        }));

    new Setting(containerEl)
      .setName(text("Inbox 轮询间隔（分钟）", "Inbox interval (minutes)"))
      .addText((input) => input
        .setValue(String(this.plugin.settings.inboxIntervalMinutes))
        .onChange(async (value) => {
          const parsed = Number(value);
          if (Number.isFinite(parsed) && parsed >= 1) {
            this.plugin.settings.inboxIntervalMinutes = Math.trunc(parsed);
            await this.plugin.saveSettings();
          }
        }));

    new Setting(containerEl)
      .setName(text("每日运行时间", "Daily local time"))
      .setDesc("Asia/Shanghai, HH:mm")
      .addText((input) => input
        .setValue(this.plugin.settings.dailyLocalTime)
        .onChange(async (value) => {
          try {
            parseLocalTime(value);
            this.plugin.settings.dailyLocalTime = value;
            await this.plugin.saveSettings();
          } catch {
            // Keep the last valid value.
          }
        }));

    new Setting(containerEl)
      .setName(text("启动后补跑错过的每日流程", "Catch up missed daily run after startup"))
      .addToggle((toggle) => toggle
        .setValue(this.plugin.settings.catchUpDailyAfterStartup)
        .onChange(async (value) => {
          this.plugin.settings.catchUpDailyAfterStartup = value;
          await this.plugin.saveSettings();
        }));

    containerEl.createEl("pre", { text: this.plugin.statusSummary() });
  }
}

module.exports = PaperFlowAutomationPlugin;
module.exports.__test = {
  controlCommands,
  githubUrl,
  isInboxRequestPath,
  mergedSettings,
  intervalDue,
  isChinese,
  text
};
