/* global Zotero */

"use strict";

const observers = [];
const annotationTimers = new Map();
const projectionTimers = new Map();
let menuItem = null;
let collectionMenuItem = null;
let migrateMenuItem = null;
let migrationSnapshotMenuItem = null;
let annotationSyncMenuItem = null;
let importCorePaperMenuItem = null;
let connectMenuItem = null;
let analyzeMenuItem = null;
let markdownMenuItem = null;
let subscriptionMenuItem = null;
let subscriptionInboxMenuItem = null;
let subscriptionImportMenuItem = null;
let communityMenuItem = null;
let communityPublishMenuItem = null;
let controlCenterMenuItem = null;
let coreClient = null;
let zoteroUi = null;
let readerIntegration = null;
let controlCenter = null;
let services = null;
let pluginRootURI = "";
let zoteroApiLoaded = false;

try {
  services = ChromeUtils.importESModule("resource://gre/modules/Services.sys.mjs").Services;
} catch (_error) {
  // Older Zotero 7 builds expose Services.jsm through the legacy loader.
  try {
    services = ChromeUtils.import("resource://gre/modules/Services.jsm").Services;
  } catch (_legacyError) {}
}
// Zotero 9 bootstrap sandboxes can expose Services as an injected global even
// when direct module imports are unavailable.  Keep this fallback before any
// dialog or script-loader call so menu actions never silently no-op.
if (!services && typeof globalThis.Services !== "undefined") {
  services = globalThis.Services;
}
if (!services && typeof Components !== "undefined") {
  try {
    // Zotero 9 can withhold Services.sys.mjs from a bootstrap sandbox while
    // still exposing the supported XPCOM services. Build only the small
    // service surface PaperFlow needs instead of falling back to the removed
    // ChromeUtils.import().
    services = {
      io: Components.classes["@mozilla.org/network/io-service;1"]
        .getService(Components.interfaces.nsIIOService),
      scriptloader: Components.classes["@mozilla.org/moz/jssubscript-loader;1"]
        .getService(Components.interfaces.mozIJSSubScriptLoader),
      prompt: Components.classes["@mozilla.org/embedcomp/prompt-service;1"]
        .getService(Components.interfaces.nsIPromptService),
    };
  } catch (_xpcomError) {
    services = null;
  }
}

function nativePromptService() {
  if (services?.prompt) return services.prompt;
  try {
    if (typeof Components !== "undefined") {
      return Components.classes["@mozilla.org/embedcomp/prompt-service;1"]
        .getService(Components.interfaces.nsIPromptService);
    }
  } catch (error) {
    try { Zotero.debug?.(`PaperFlow prompt service unavailable: ${error}`); } catch (_debugError) {}
  }
  return null;
}

function rememberPluginRoot(data = {}) {
  const value = String(data?.rootURI || "").trim();
  if (value) pluginRootURI = value.endsWith("/") ? value : `${value}/`;
  return pluginRootURI;
}

function pluginScriptURI(relativePath) {
  const relative = String(relativePath || "").replace(/^\/+/, "");
  if (pluginRootURI) return `${pluginRootURI}${relative}`;
  if (typeof __SCRIPT_URI_SPEC__ !== "undefined" && services?.io) {
    const uri = services.io.newURI(__SCRIPT_URI_SPEC__);
    uri.pathQueryRef = uri.pathQueryRef.replace(
      /bootstrap\.js(?:\?.*)?$/,
      relative
    );
    return uri.spec;
  }
  return "";
}

function notify(message) {
  if (typeof Zotero !== "undefined" && Zotero.alert) {
    Zotero.alert(null, "PaperFlow", message);
    return;
  }
  const prompt = nativePromptService();
  if (prompt && typeof prompt.alert === "function") {
    prompt.alert(null, "PaperFlow", message);
    return;
  }
  const win = typeof Zotero !== "undefined" && Zotero.getMainWindow
    ? Zotero.getMainWindow()
    : null;
  if (win && typeof win.alert === "function") {
    win.alert(`PaperFlow\n\n${message}`);
  }
}

function prefGet(name, fallback = "") {
  try {
    const prefs = Zotero && Zotero.Prefs;
    if (prefs && typeof prefs.get === "function") return prefs.get(name, fallback) || fallback;
  } catch (_error) {}
  return fallback;
}

function prefSet(name, value) {
  const prefs = Zotero && Zotero.Prefs;
  if (prefs && typeof prefs.set === "function") prefs.set(name, value);
}

function loadCoreClient() {
  if (typeof globalThis.PaperFlowCoreClient === "function") {
    return globalThis.PaperFlowCoreClient;
  }
  if (!services?.scriptloader) return null;
  try {
    const uri = pluginScriptURI("src/core-client.js");
    if (!uri) return null;
    services.scriptloader.loadSubScript(uri, globalThis);
    return typeof globalThis.PaperFlowCoreClient === "function"
      ? globalThis.PaperFlowCoreClient
      : null;
  } catch (error) {
    try { Zotero.debug?.(`PaperFlow Core client load failed: ${error}`); } catch (_debugError) {}
    return null;
  }
}

function configuredCore() {
  const Client = loadCoreClient();
  if (!Client) return null;
  try {
    return new Client(
      prefGet("extensions.paperflow-zotero.coreBaseUrl", "http://127.0.0.1:23140"),
      prefGet("extensions.paperflow-zotero.coreToken", ""),
      {
        pairingId: prefGet("extensions.paperflow-zotero.pairingId", ""),
        pairingSecret: prefGet("extensions.paperflow-zotero.pairingSecret", ""),
        onSession: (token) => {
          prefSet("extensions.paperflow-zotero.coreToken", token);
        },
      }
    );
  } catch (_error) { return null; }
}

async function coreStatus() {
  coreClient = configuredCore();
  if (!coreClient) {
    notify("PaperFlow Core：尚未配对。请使用“连接 Core”完成一次本机配对。");
    return;
  }
  try {
    const value = await coreClient.health();
    if (!value || !value.ok) {
      notify("PaperFlow Core：不可用");
      return;
    }
    let detail = "暂无任务";
    try {
      const jobs = await coreClient.jobs(5);
      const records = Array.isArray(jobs?.jobs) ? jobs.jobs : [];
      if (records.length) {
        detail = records.map((job) => `${job.kind || "job"}=${job.status || "?"}`).join("，");
      }
    } catch (_error) {
      detail = "任务状态暂不可读";
    }
    notify(`PaperFlow Core：已连接；${detail}`);
  } catch (error) {
    notify(`PaperFlow Core：${error.message || error}`);
  }
}

function promptValue(title, message, initial = "") {
  const prompt = nativePromptService();
  if (prompt && typeof prompt.prompt === "function") {
    const input = { value: initial };
    const accepted = prompt.prompt(null, title, message, input, null, {});
    return accepted ? String(input.value || "").trim() : null;
  }
  // A main-window prompt remains available in Zotero 9 bootstrap sandboxes
  // where Services is not injected.  Returning null without this fallback
  // made "连接 Core" appear to do nothing.
  const win = typeof Zotero !== "undefined" && Zotero.getMainWindow
    ? Zotero.getMainWindow()
    : null;
  if (win && typeof win.prompt === "function") {
    const value = win.prompt(`${title}\n\n${message}`, initial);
    return value === null ? null : String(value || "").trim();
  }
  notify("无法打开输入对话框。请在“帮助 → 调试输出日志”中查看插件错误。");
  return null;
}

function confirmAction(title, message) {
  if (services?.prompt?.confirm) return services.prompt.confirm(null, title, message);
  const answer = promptValue(title, `${message}\n请输入 YES 确认：`, "");
  return String(answer || "").trim().toUpperCase() === "YES";
}

async function configureCore() {
  const baseUrl = promptValue("PaperFlow Core", "请输入 loopback Core 地址：", prefGet("extensions.paperflow-zotero.coreBaseUrl", "http://127.0.0.1:23140"));
  if (baseUrl === null) return;
  const token = promptValue("PaperFlow Core", "请输入 Core 会话令牌（不会写入 Vault）：", "");
  if (token === null) return;
  try {
    const Client = loadCoreClient();
    if (typeof Client !== "function") {
      throw new Error("Core client 模块加载失败；请重载 PaperFlow 插件");
    }
    coreClient = new Client(baseUrl, token, {
      onSession: (value) => {
        prefSet("extensions.paperflow-zotero.coreToken", value);
      },
    });
    // /health is intentionally public and cannot validate a token. Read one
    // protected endpoint before claiming the connection succeeded.
    await coreClient.jobs(1);
    const pairing = await coreClient.createPairing("PaperFlow for Zotero");
    prefSet("extensions.paperflow-zotero.coreBaseUrl", coreClient.baseUrl);
    prefSet("extensions.paperflow-zotero.coreToken", coreClient.token);
    prefSet("extensions.paperflow-zotero.pairingId", pairing.pairing_id);
    prefSet("extensions.paperflow-zotero.pairingSecret", pairing.pairing_secret);
    notify("PaperFlow Core：配对已保存；以后 Core 重启会自动续期会话。");
  } catch (error) {
    coreClient = null;
    notify(`PaperFlow Core：连接失败：${error.message || error}`);
  }
}

function loadZoteroApi() {
  // A Zotero bootstrap reload can preserve globals from the previous
  // sandbox. Load the adapter once per bootstrap startup even when a stale
  // PaperFlowZoteroApi constructor is already present.
  if (!zoteroApiLoaded && services?.scriptloader) {
    try {
      const uri = pluginScriptURI("src/zotero-api.js");
      if (uri) services.scriptloader.loadSubScript(uri, globalThis);
      zoteroApiLoaded = true;
    } catch (_error) {}
  }
  return typeof globalThis.PaperFlowZoteroApi === "function"
    ? globalThis.PaperFlowZoteroApi
    : null;
}

function loadZoteroUi() {
  if (typeof globalThis.PaperFlowZoteroUi === "function") {
    return globalThis.PaperFlowZoteroUi;
  }
  if (!services?.scriptloader) return null;
  try {
    const uri = pluginScriptURI("src/ui.js");
    if (!uri) return null;
    services.scriptloader.loadSubScript(uri, globalThis);
    return typeof globalThis.PaperFlowZoteroUi === "function"
      ? globalThis.PaperFlowZoteroUi
      : null;
  } catch (_error) {
    return null;
  }
}

async function ensurePaperFlowCollection() {
  const Api = loadZoteroApi();
  if (!Api) {
    notify("PaperFlow：当前 Zotero 版本未提供可加载的公开 API 适配器。");
    return;
  }
  try {
    const result = await new Api(Zotero).ensureCollection("PaperFlow");
    notify(`PaperFlow Collection：${result.status === "created" ? "已创建" : "已复用"}`);
  } catch (error) {
    notify(`PaperFlow Collection：${error.message || error}`);
  }
}

async function addSelectedItemsToPaperFlow() {
  const Api = loadZoteroApi();
  if (!Api) {
    notify("PaperFlow：当前 Zotero 版本未提供可加载的公开 API 适配器。");
    return;
  }
  try {
    const result = await new Api(Zotero).ensureSelectedItemsInCollection("PaperFlow");
    if (result.status === "no-selection") {
      notify("PaperFlow：请先在条目列表中选择论文条目。");
      return;
    }
    const added = (result.added || []).filter((item) => item.status === "added").length;
    const existing = (result.added || []).filter((item) => item.status === "already-member").length;
    notify(`PaperFlow Collection：已加入 ${added} 篇，已存在 ${existing} 篇`);
  } catch (error) {
    notify(`PaperFlow Collection：${error.message || error}`);
  }
}

async function publishZoteroEvent(itemKey, options = {}) {
  if (!coreClient) coreClient = configuredCore();
  const Api = loadZoteroApi();
  if (!coreClient || !Api) return { ok: false, reason: "core-not-configured" };
  const payload = await new Api(Zotero).eventPayload(itemKey, "modify", options);
  const response = await coreClient.sendEvent(payload);
  scheduleProjectionJob(itemKey, response, {
    notifyOnComplete: Boolean(options.notifyOnComplete),
  });
  return response;
}

async function syncAiMarkdownProjection(itemKey) {
  if (!coreClient) coreClient = configuredCore();
  const Api = loadZoteroApi();
  if (!coreClient || !Api) throw new Error("Core is not configured");
  const api = new Api(Zotero);
  const item = await api.getItemByKey(itemKey);
  if (!item || item.isAttachment?.() || item.isNote?.()) {
    throw new Error("Zotero parent item is unavailable");
  }
  const paperUid = api.paperUid(item);
  if (!paperUid) throw new Error("Zotero item has no resolved paper identity");
  const rendered = await coreClient.aiMarkdown(paperUid, String(item.key || itemKey));
  if (!rendered?.content) throw new Error("Core did not return AI Markdown");
  const attached = await api.attachAiMarkdown(item, rendered.content, {
    filename: rendered.filename,
    sha256: rendered.content_sha256,
  });
  const snapshot = await api.migrationSnapshot([item], "PaperFlow");
  const migration = await coreClient.migrationResults(snapshot);
  if (!(migration.mappings || []).length) {
    const rejected = (migration.rejected || []).find(
      (value) => value?.paper_uid === paperUid
    );
    throw new Error(
      `Core rejected the post-projection mapping${rejected?.reason ? `: ${rejected.reason}` : ""}`
    );
  }
  return { attached, migration, paperUid };
}

function scheduleProjectionJob(itemKey, response, options = {}) {
  const jobId = String(response?.job?.job_id || "");
  if (!jobId || projectionTimers.has(jobId)) return false;
  const deadline = Date.now() + 30 * 60 * 1000;
  let delay = 750;
  const poll = async () => {
    projectionTimers.delete(jobId);
    try {
      if (!coreClient) coreClient = configuredCore();
      if (!coreClient) return;
      const job = await coreClient.job(jobId);
      if (job?.status === "completed") {
        const result = await syncAiMarkdownProjection(itemKey);
        if (options.notifyOnComplete) {
          notify(
            `PaperFlow AI Markdown：${result.attached.status === "up-to-date" ? "已是最新" : "已附加到 Zotero"}；Obsidian 主投影已同步。`
          );
        }
        return;
      }
      if (job?.status === "failed" || job?.status === "skipped") {
        notify(`PaperFlow 分析/呈现失败：${job.error || job.status}`);
        return;
      }
      if (Date.now() >= deadline) {
        notify("PaperFlow 分析仍在运行；可在控制中心继续查看状态。");
        return;
      }
      delay = Math.min(5000, Math.round(delay * 1.5));
      projectionTimers.set(jobId, setTimeout(poll, delay));
    } catch (error) {
      if (Date.now() >= deadline) {
        Zotero.debug?.(`PaperFlow projection polling stopped: ${error}`);
        return;
      }
      delay = Math.min(5000, Math.round(delay * 1.5));
      projectionTimers.set(jobId, setTimeout(poll, delay));
    }
  };
  projectionTimers.set(jobId, setTimeout(poll, delay));
  return true;
}

async function publishAnnotation(itemKey, event = "modify") {
  if (!coreClient) coreClient = configuredCore();
  const Api = loadZoteroApi();
  if (!coreClient || !Api) return { ok: false, reason: "core-not-configured" };
  const payload = await new Api(Zotero).annotationPayload(itemKey, event);
  if (!payload) return { ok: false, reason: "not-an-annotation" };
  return coreClient.mirrorAnnotation(payload);
}

function scheduleAnnotationMirror(ids, event = "modify") {
  for (const rawKey of ids || []) {
    const key = String(rawKey || "");
    if (!key) continue;
    const previous = annotationTimers.get(key);
    if (previous) clearTimeout(previous);
    const timer = setTimeout(async () => {
      annotationTimers.delete(key);
      try { await publishAnnotation(key, event); } catch (error) { Zotero.debug?.(`PaperFlow annotation mirror failed: ${error}`); }
    }, 500);
    annotationTimers.set(key, timer);
  }
}

async function syncSelectedAnnotations() {
  if (!coreClient) coreClient = configuredCore();
  const Api = loadZoteroApi();
  if (!coreClient || !Api) {
    notify("PaperFlow：请先连接 Core，再同步标注。");
    return;
  }
  const win = Zotero.getMainWindow?.();
  const selected = win?.ZoteroPane?.getSelectedItems?.() || [];
  if (!selected.length) {
    notify("PaperFlow：请先选择论文、PDF 或标注。");
    return;
  }
  try {
    const api = new Api(Zotero);
    const annotations = await api.annotationsForItems(selected);
    let mirrored = 0;
    for (const annotation of annotations) {
      const result = await publishAnnotation(String(annotation.key || annotation.id || ""));
      if (result?.ok) mirrored += 1;
    }
    notify(`PaperFlow 标注同步：发现 ${annotations.length} 条，已镜像 ${mirrored} 条。`);
  } catch (error) {
    notify(`PaperFlow 标注同步失败：${error.message || error}`);
  }
}

async function analyzeSelectedItems() {
  if (!coreClient) coreClient = configuredCore();
  const Api = loadZoteroApi();
  if (!coreClient || !Api) {
    notify("PaperFlow：请先连接 Core，再从选中条目触发分析。");
    return;
  }
  const api = new Api(Zotero);
  const selected = api.selectedItems();
  if (!selected.length) {
    notify("PaperFlow：请先选择论文条目。");
    return;
  }
  let queued = 0;
  let skipped = 0;
  for (const item of selected) {
    let snapshot;
    try {
      snapshot = api.paperSnapshot(item);
      const attachment = await api.pdfAttachment(item);
      if (!attachment) {
        skipped += 1;
        Zotero.debug?.(`PaperFlow analysis skipped ${item.key || "?"}: no PDF attachment`);
        continue;
      }
      await coreClient.importPaper(snapshot);
      const chunkSize = 768 * 1024;
      for (let offset = 0; offset < attachment.bytes.byteLength; offset += chunkSize) {
        const chunk = attachment.bytes.subarray(offset, Math.min(offset + chunkSize, attachment.bytes.byteLength));
        await coreClient.uploadPdfChunk(snapshot.paper_uid, chunk, {
          offset,
          total: attachment.bytes.byteLength,
          sha256: attachment.sha256,
          filename: attachment.filename,
          itemKey: String(item.key || ""),
        });
      }
      await coreClient.enqueueAnalysis({
        paper_uid: snapshot.paper_uid,
        zotero_item_key: String(item.key || ""),
        trigger: "zotero-manual",
        analysis_profile: prefGet("extensions.paperflow-zotero.analysisProfile", "full_analysis"),
        target: prefGet("extensions.paperflow-zotero.analysisTarget", "zotero"),
      });
      queued += 1;
    } catch (error) {
      Zotero.debug?.(`PaperFlow analysis enqueue failed: ${error}`);
    }
  }
  notify(`PaperFlow 导入并分析：已排队 ${queued} 篇${skipped ? `，跳过 ${skipped} 篇（缺少可验证 PDF 或身份）` : ""}`);
}

async function attachSelectedAiMarkdown() {
  if (!coreClient) coreClient = configuredCore();
  const Api = loadZoteroApi();
  if (!coreClient || !Api) { notify("PaperFlow：请先连接 Core，再附加 AI Markdown。"); return; }
  const api = new Api(Zotero);
  const selected = api.selectedItems();
  if (!selected.length) { notify("PaperFlow：请先选择一篇论文条目。"); return; }
  let created = 0;
  let current = 0;
  for (const item of selected.slice(0, 20)) {
    try {
      const paperUid = api.paperUid(item);
      if (!paperUid) throw new Error("缺少可验证 arXiv/DOI 身份");
      const rendered = await coreClient.aiMarkdown(paperUid, String(item.key || ""));
      if (!rendered?.content) throw new Error("Core 未返回 AI Markdown");
      const result = await api.attachAiMarkdown(item, rendered.content, { filename: rendered.filename, sha256: rendered.content_sha256 });
      if (result.status === "up-to-date") current += 1; else created += 1;
    } catch (error) { Zotero.debug?.(`PaperFlow AI Markdown attachment failed: ${error}`); }
  }
  notify(`PaperFlow AI Markdown：${created ? `已新增 ${created} 个附件` : "没有新增附件"}${current ? `，${current} 个已是最新` : ""}。用户已有附件不会被覆盖。`);
}

function loadZoteroReader() {
  if (typeof globalThis.PaperFlowReaderIntegration === "function") {
    return globalThis.PaperFlowReaderIntegration;
  }
  if (!services?.scriptloader) return null;
  try {
    const uri = pluginScriptURI("src/reader.js");
    if (!uri) return null;
    services.scriptloader.loadSubScript(uri, globalThis);
    return typeof globalThis.PaperFlowReaderIntegration === "function"
      ? globalThis.PaperFlowReaderIntegration
      : null;
  } catch (_error) { return null; }
}

function loadControlCenter() {
  if (typeof globalThis.PaperFlowControlCenter === "function") {
    return globalThis.PaperFlowControlCenter;
  }
  if (!services?.scriptloader) return null;
  try {
    const uri = pluginScriptURI("src/control-center.js");
    if (!uri) return null;
    services.scriptloader.loadSubScript(uri, globalThis);
    return typeof globalThis.PaperFlowControlCenter === "function"
      ? globalThis.PaperFlowControlCenter
      : null;
  } catch (_error) { return null; }
}

function openControlCenter() {
  if (!controlCenter) {
    const Center = loadControlCenter();
    if (!Center) { notify("PaperFlow：当前 Zotero 版本不支持控制中心。"); return; }
    controlCenter = new Center(Zotero, {
      clientProvider: () => { if (!coreClient) coreClient = configuredCore(); return coreClient; },
      reader: readerIntegration,
      notify,
      actions: {
        configureCore,
        importPaper: importPaperFromCore,
        analyze: analyzeSelectedItems,
        attachAiMarkdown: attachSelectedAiMarkdown,
        syncSubscriptions,
        subscriptionInbox: () => subscriptionInboxAction({ importPaper: false }),
        communityPreview: () => previewCommunitySelected({ publish: false }),
      },
    });
  }
  try {
    if (!controlCenter.open()) {
      notify("PaperFlow 控制中心：Zotero 主窗口尚未就绪。");
    }
  } catch (error) {
    try { Zotero.debug?.(`PaperFlow control center failed: ${error?.stack || error}`); } catch (_debugError) {}
    notify(`PaperFlow 控制中心：打开失败：${error?.message || error}`);
  }
}

async function syncSubscriptions() {
  if (!coreClient) coreClient = configuredCore();
  if (!coreClient) {
    notify("PaperFlow：请先连接 Core，再同步订阅。");
    return;
  }
  try {
    const result = await coreClient.syncSubscriptions({ trigger: "zotero-menu" });
    notify(`PaperFlow 订阅：${result.status === "queued" ? "已排队" : result.status || "已提交"}`);
  } catch (error) {
    notify(`PaperFlow 订阅：${error.message || error}`);
  }
}

async function buildCommunityContribution(api, annotation) {
  const annotationPayload = await api.annotationPayload(String(annotation.key || annotation.id || ""));
  if (!annotationPayload || !annotationPayload.paper_uid) {
    throw new Error("选中的条目不是可发布的 Zotero 标注，或缺少论文身份");
  }
  const creator = prefGet("extensions.paperflow-zotero.communityCreator", "reader");
  const license = prefGet("extensions.paperflow-zotero.communityLicense", "CC-BY-4.0");
  if (!/^[A-Za-z0-9-]{1,39}$/.test(creator)) throw new Error("社区发布者标识无效，请在 Zotero 偏好中设置 ASCII 标识");
  if (!license) throw new Error("社区许可证不能为空");
  const body = String(annotationPayload.comment || annotationPayload.text || "").trim();
  if (!body) throw new Error("标注没有可公开的文本或评论");
  let pdfSha256 = "";
  try {
    const status = await coreClient.itemStatus(annotationPayload.parent_item_key);
    const attachments = status?.mapping?.zotero?.attachments || [];
    pdfSha256 = String(attachments.find((item) => item && /^[a-f0-9]{64}$/i.test(String(item.sha256 || "")))?.sha256 || "").toLowerCase();
  } catch (_error) {}
  const page = Number.parseInt(String(annotationPayload.page || ""), 10);
  const anchor = pdfSha256 && Number.isInteger(page) && page > 0
    ? { pdf_version: 1, pdf_sha256: pdfSha256, page, exact_quote: String(annotationPayload.text || "").slice(0, 500) }
    : null;
  return {
    paper_uid: annotationPayload.paper_uid,
    contribution: {
      contribution_id: `zotero-${annotationPayload.annotation_id}`,
      paper_uid: annotationPayload.paper_uid,
      kind: annotationPayload.comment ? "passage-comment" : "highlight",
      body,
      tags: Array.isArray(annotationPayload.tags) ? annotationPayload.tags : [],
      anchor,
      created_at: annotationPayload.created_at || new Date().toISOString(),
    },
    creator,
    license,
  };
}

async function subscriptionInboxAction({ importPaper = false } = {}) {
  if (!coreClient) coreClient = configuredCore();
  const Api = loadZoteroApi();
  if (!coreClient || !Api) {
    notify("PaperFlow：请先连接 Core，再查看订阅 Inbox。");
    return;
  }
  try {
    const inbox = await coreClient.subscriptionInbox({ status: "pending-confirmation", limit: 100 });
    const items = Array.isArray(inbox?.items) ? inbox.items : [];
    if (!items.length) {
      notify("PaperFlow 订阅 Inbox：当前没有待确认论文。");
      return;
    }
    const first = items[0];
    const listed = items.slice(0, 8).map((item) => `${item.paper_uid}: ${item.title || "未命名"}`).join("\n");
    const selectedUid = items.length === 1
      ? String(first.paper_uid)
      : promptValue("PaperFlow 订阅 Inbox", `待确认 ${items.length} 篇，请输入 paper_uid：\n${listed}`, String(first.paper_uid));
    if (!selectedUid) return;
    const selected = await coreClient.subscriptionInboxItem(selectedUid);
    if (!selected?.paper?.paper_uid) throw new Error("订阅 Inbox 返回的论文身份无效");
    if (!importPaper) {
      notify(`PaperFlow 订阅 Inbox：${selected.paper.paper_uid}；${selected.paper.paper_title || "未命名"}。再次选择“确认导入”才会写入 Zotero。`);
      return;
    }
    if (!confirmAction("PaperFlow 订阅导入", `将通过 Zotero 公开对象 API 创建/复用条目并加入 PaperFlow Collection：\n${selected.paper.paper_title || selected.paper.paper_uid}\n\n仅导入元数据，不自动下载 PDF。确认吗？`)) {
      notify("PaperFlow 订阅导入：已取消。");
      return;
    }
    const api = new Api(Zotero);
    const created = await api.createBibliographicItem(selected.paper, "PaperFlow");
    const item = created.item;
    const snapshot = await api.migrationSnapshot([item], "PaperFlow");
    await coreClient.migrationResults(snapshot);
    await coreClient.subscriptionDecision({
      paper_uid: selected.paper.paper_uid,
      decision: "imported",
      item_key: String(item.key || ""),
    });
    notify(`PaperFlow 订阅导入：${created.status === "created" ? "已创建" : "已复用"} Zotero 条目并完成映射。`);
  } catch (error) {
    notify(`PaperFlow 订阅 Inbox：${error.message || error}`);
  }
}

async function previewCommunitySelected({ publish = false } = {}) {
  if (!coreClient) coreClient = configuredCore();
  const Api = loadZoteroApi();
  if (!coreClient || !Api) {
    notify("PaperFlow：请先连接 Core，再发布社区标注。");
    return;
  }
  const api = new Api(Zotero);
  const selected = api.selectedAnnotations();
  if (!selected.length) { notify("PaperFlow：请先在 Zotero 中选择一个标注条目。"); return; }
  try {
    const request = await buildCommunityContribution(api, selected[0]);
    const plan = await coreClient.communityPlan({
      paper_uid: request.paper_uid,
      contribution: request.contribution,
      creator: request.creator,
      license: request.license,
      trigger: "zotero-menu",
    });
    if (!publish) {
      notify(`PaperFlow 社区发布：预览通过，${plan.contribution?.anchor ? "已验证 PDF 锚点" : "未找到可验证 PDF 哈希，使用无锚点快照"}；再次选择“确认发布”才会写入 outbox。`);
      return;
    }
    const accepted = confirmAction("PaperFlow 社区发布", "仅会写入本机 outbox，不会自动 push GitHub。确认发布选中的标注吗？");
    if (!accepted) { notify("PaperFlow 社区发布：已取消，没有写入 outbox。"); return; }
    const result = await coreClient.publishCommunity({
      paper_uid: request.paper_uid,
      contribution: request.contribution,
      creator: request.creator,
      license: request.license,
      confirm: true,
    });
    notify(`PaperFlow 社区发布：${result.status === "outbox-written" ? "已写入本机 outbox" : result.status || "已完成"}；不会自动 push GitHub。`);
  } catch (error) {
    notify(`PaperFlow 社区发布：${error.message || error}`);
  }
}

async function syncMigrationSnapshot() {
  if (!coreClient) coreClient = configuredCore();
  const Api = loadZoteroApi();
  if (!coreClient || !Api) {
    notify("PaperFlow：请先连接 Core，再同步 Zotero 身份/附件校验结果。");
    return;
  }
  try {
    const api = new Api(Zotero);
    const snapshot = await api.migrationSnapshot();
    const eligible = (snapshot.items || []).filter((item) => item.paper_uid && item.item_key);
    if (!eligible.length) {
      notify("PaperFlow：当前没有可同步的论文身份。");
      return;
    }
    snapshot.items = eligible;
    const result = await coreClient.migrationResults(snapshot);
    notify(`PaperFlow 映射：已接收 ${result.mappings?.length || 0} 项${result.rejected?.length ? `，拒绝 ${result.rejected.length} 项` : ""}`);
  } catch (error) {
    notify(`PaperFlow 映射同步失败：${error.message || error}`);
  }
}

async function importPaperFromCore() {
  if (!coreClient) coreClient = configuredCore();
  const Api = loadZoteroApi();
  if (!coreClient || !Api) {
    notify("PaperFlow：请先连接 Core，再从 PaperFlow 导入论文。");
    return;
  }
  const paperUid = promptValue(
    "PaperFlow 导入论文",
    "请输入 PaperFlow paper_uid（例如 arxiv:2504.16054）：",
    ""
  );
  if (!paperUid) return;
  try {
    const result = await coreClient.getPaper(paperUid);
    const paper = result?.paper;
    if (!result?.ok || !paper?.paper_uid || !paper?.paper_title) {
      throw new Error("Core 中未找到可导入的 canonical paper");
    }
    const accepted = confirmAction(
      "PaperFlow 导入论文",
      `将通过 Zotero 公开对象 API 创建或复用条目、加入 PaperFlow Collection，并导入 Core 中经过校验的 PDF：\n${paper.paper_title}\n\n不会修改主库之外的文件，也不会删除原 PDF。确认吗？`
    );
    if (!accepted) {
      notify("PaperFlow 导入论文：已取消。");
      return;
    }
    const api = new Api(Zotero);
    const created = await api.createBibliographicItem(paper, "PaperFlow");
    const downloaded = await coreClient.paperPdf(paper.paper_uid);
    const attached = await api.attachStoredPdf(created.item, downloaded.bytes, {
      filename: downloaded.filename,
      sha256: downloaded.sha256,
    });
    const snapshot = await api.migrationSnapshot([created.item], "PaperFlow");
    const migration = await coreClient.migrationResults(snapshot);
    const mapped = (migration.mappings || []).length > 0;
    if (!mapped) {
      const rejected = (migration.rejected || []).find(
        (value) => value?.paper_uid === paper.paper_uid
      );
      throw new Error(
        `Core 未接受 Zotero mapping${rejected?.reason ? `：${rejected.reason}` : ""}`
      );
    }
    const pipeline = await publishZoteroEvent(
      String(created.item?.key || ""),
      {
        collectionName: "PaperFlow",
        analysisProfile: prefGet(
          "extensions.paperflow-zotero.analysisProfile",
          "full_analysis"
        ),
        notifyOnComplete: true,
      }
    );
    try {
      const win = Zotero.getMainWindow?.();
      if (created.item?.id && win?.ZoteroPane?.selectItem) {
        await win.ZoteroPane.selectItem(created.item.id);
      }
    } catch (_error) {}
    notify(
      `PaperFlow 导入论文：条目${created.status === "created" ? "已创建" : "已复用"}，` +
      `PDF ${attached.status === "up-to-date" ? "已存在" : "已导入"}，` +
      `映射 ${migration.mappings?.length || 0} 项；` +
      `${pipeline?.pipeline?.reuse_analysis ? "已复用既有分析并开始双端呈现" : "分析已进入事件流水线"}。`
    );
  } catch (error) {
    notify(`PaperFlow 导入论文失败：${error.message || error}`);
  }
}

function addMenuItem() {
  if (typeof Zotero === "undefined" || !Zotero.getMainWindow) return;
  const win = Zotero.getMainWindow();
  if (!win || !win.document) return;
  const menu = win.document.getElementById("zotero-itemmenu");
  if (!menu || menuItem) return;
  menuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  menuItem.id = "paperflow-zotero-status";
  menuItem.setAttribute("label", "PaperFlow：查看状态");
  menuItem.addEventListener("command", coreStatus);
  menu.appendChild(menuItem);
  collectionMenuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  collectionMenuItem.id = "paperflow-zotero-ensure-collection";
  collectionMenuItem.setAttribute("label", "PaperFlow：创建/复用 Collection");
  collectionMenuItem.addEventListener("command", ensurePaperFlowCollection);
  menu.appendChild(collectionMenuItem);
  migrateMenuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  migrateMenuItem.id = "paperflow-zotero-add-selection";
  migrateMenuItem.setAttribute("label", "PaperFlow：将选中论文加入 Collection");
  migrateMenuItem.addEventListener("command", addSelectedItemsToPaperFlow);
  menu.appendChild(migrateMenuItem);
  migrationSnapshotMenuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  migrationSnapshotMenuItem.id = "paperflow-zotero-sync-migration-snapshot";
  migrationSnapshotMenuItem.setAttribute("label", "PaperFlow：同步身份与附件校验");
  migrationSnapshotMenuItem.addEventListener("command", syncMigrationSnapshot);
  menu.appendChild(migrationSnapshotMenuItem);
  annotationSyncMenuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  annotationSyncMenuItem.id = "paperflow-zotero-sync-annotations";
  annotationSyncMenuItem.setAttribute("label", "PaperFlow：同步选中论文标注");
  annotationSyncMenuItem.addEventListener("command", syncSelectedAnnotations);
  menu.appendChild(annotationSyncMenuItem);
  importCorePaperMenuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  importCorePaperMenuItem.id = "paperflow-zotero-import-core-paper";
  importCorePaperMenuItem.setAttribute("label", "PaperFlow：从 Core 导入论文及 PDF");
  importCorePaperMenuItem.addEventListener("command", importPaperFromCore);
  menu.appendChild(importCorePaperMenuItem);
  connectMenuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  connectMenuItem.id = "paperflow-zotero-connect-core";
  connectMenuItem.setAttribute("label", "PaperFlow：连接 Core");
  connectMenuItem.addEventListener("command", configureCore);
  menu.appendChild(connectMenuItem);
  analyzeMenuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  analyzeMenuItem.id = "paperflow-zotero-analyze-selection";
  analyzeMenuItem.setAttribute("label", "PaperFlow：导入并分析选中论文");
  analyzeMenuItem.addEventListener("command", analyzeSelectedItems);
  menu.appendChild(analyzeMenuItem);
  markdownMenuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  markdownMenuItem.id = "paperflow-zotero-attach-ai-markdown";
  markdownMenuItem.setAttribute("label", "PaperFlow：附加 AI Markdown");
  markdownMenuItem.addEventListener("command", attachSelectedAiMarkdown);
  menu.appendChild(markdownMenuItem);
  subscriptionMenuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  subscriptionMenuItem.id = "paperflow-zotero-sync-subscriptions";
  subscriptionMenuItem.setAttribute("label", "PaperFlow：同步订阅预览");
  subscriptionMenuItem.addEventListener("command", syncSubscriptions);
  menu.appendChild(subscriptionMenuItem);
  subscriptionInboxMenuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  subscriptionInboxMenuItem.id = "paperflow-zotero-subscription-inbox";
  subscriptionInboxMenuItem.setAttribute("label", "PaperFlow：查看订阅 Inbox");
  subscriptionInboxMenuItem.addEventListener("command", () => subscriptionInboxAction({ importPaper: false }));
  menu.appendChild(subscriptionInboxMenuItem);
  subscriptionImportMenuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  subscriptionImportMenuItem.id = "paperflow-zotero-subscription-import";
  subscriptionImportMenuItem.setAttribute("label", "PaperFlow：确认导入订阅论文");
  subscriptionImportMenuItem.addEventListener("command", () => subscriptionInboxAction({ importPaper: true }));
  menu.appendChild(subscriptionImportMenuItem);
  communityMenuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  communityMenuItem.id = "paperflow-zotero-community-preview";
  communityMenuItem.setAttribute("label", "PaperFlow：预览选中标注的社区发布");
  communityMenuItem.addEventListener("command", previewCommunitySelected);
  menu.appendChild(communityMenuItem);
  communityPublishMenuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  communityPublishMenuItem.id = "paperflow-zotero-community-publish";
  communityPublishMenuItem.setAttribute("label", "PaperFlow：确认发布选中标注");
  communityPublishMenuItem.addEventListener("command", () => previewCommunitySelected({ publish: true }));
  menu.appendChild(communityPublishMenuItem);
  controlCenterMenuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  controlCenterMenuItem.id = "paperflow-zotero-control-center";
  controlCenterMenuItem.setAttribute("label", "PaperFlow：打开控制中心");
  controlCenterMenuItem.addEventListener("command", openControlCenter);
  menu.appendChild(controlCenterMenuItem);
}

function removeMenuItem() {
  if (menuItem && menuItem.parentNode) menuItem.parentNode.removeChild(menuItem);
  if (collectionMenuItem && collectionMenuItem.parentNode) collectionMenuItem.parentNode.removeChild(collectionMenuItem);
  if (migrateMenuItem && migrateMenuItem.parentNode) migrateMenuItem.parentNode.removeChild(migrateMenuItem);
  if (migrationSnapshotMenuItem && migrationSnapshotMenuItem.parentNode) migrationSnapshotMenuItem.parentNode.removeChild(migrationSnapshotMenuItem);
  if (annotationSyncMenuItem && annotationSyncMenuItem.parentNode) annotationSyncMenuItem.parentNode.removeChild(annotationSyncMenuItem);
  if (importCorePaperMenuItem && importCorePaperMenuItem.parentNode) importCorePaperMenuItem.parentNode.removeChild(importCorePaperMenuItem);
  if (connectMenuItem && connectMenuItem.parentNode) connectMenuItem.parentNode.removeChild(connectMenuItem);
  if (analyzeMenuItem && analyzeMenuItem.parentNode) analyzeMenuItem.parentNode.removeChild(analyzeMenuItem);
  if (markdownMenuItem && markdownMenuItem.parentNode) markdownMenuItem.parentNode.removeChild(markdownMenuItem);
  if (subscriptionMenuItem && subscriptionMenuItem.parentNode) subscriptionMenuItem.parentNode.removeChild(subscriptionMenuItem);
  if (subscriptionImportMenuItem && subscriptionImportMenuItem.parentNode) subscriptionImportMenuItem.parentNode.removeChild(subscriptionImportMenuItem);
  if (subscriptionInboxMenuItem && subscriptionInboxMenuItem.parentNode) subscriptionInboxMenuItem.parentNode.removeChild(subscriptionInboxMenuItem);
  if (communityMenuItem && communityMenuItem.parentNode) communityMenuItem.parentNode.removeChild(communityMenuItem);
  if (communityPublishMenuItem && communityPublishMenuItem.parentNode) communityPublishMenuItem.parentNode.removeChild(communityPublishMenuItem);
  if (controlCenterMenuItem && controlCenterMenuItem.parentNode) controlCenterMenuItem.parentNode.removeChild(controlCenterMenuItem);
  menuItem = null;
  collectionMenuItem = null;
  migrateMenuItem = null;
  migrationSnapshotMenuItem = null;
  annotationSyncMenuItem = null;
  importCorePaperMenuItem = null;
  connectMenuItem = null;
  analyzeMenuItem = null;
  markdownMenuItem = null;
  subscriptionMenuItem = null;
  subscriptionInboxMenuItem = null;
  subscriptionImportMenuItem = null;
  communityMenuItem = null;
  communityPublishMenuItem = null;
  controlCenterMenuItem = null;
}

function startup(data = {}) {
  if (typeof Zotero === "undefined") return;
  rememberPluginRoot(data);
  addMenuItem();
  coreClient = configuredCore();
  const Reader = loadZoteroReader();
  if (Reader) {
    readerIntegration = new Reader(Zotero, {
      clientProvider: () => { if (!coreClient) coreClient = configuredCore(); return coreClient; },
      notify,
    });
  }
  const Ui = loadZoteroUi();
  if (Ui) {
    zoteroUi = new Ui(Zotero, {
      pluginID: "paperflow-zotero@threeyang",
      rootURI: pluginRootURI,
      notify,
      openControlCenter: () => openControlCenter(),
      statusProvider: (itemKey) => {
        if (!coreClient) coreClient = configuredCore();
        return coreClient ? coreClient.itemStatus(itemKey) : Promise.resolve({ linked: false, sync: "未连接 Core" });
      },
      annotationProvider: (paperUid) => {
        if (!coreClient) coreClient = configuredCore();
        return coreClient ? coreClient.annotations(paperUid) : Promise.resolve({ count: 0 });
      },
      debounceMs: Number(prefGet("extensions.paperflow-zotero.eventDebounceMs", "10000")),
      analysisProfile: prefGet("extensions.paperflow-zotero.analysisProfile", "full_analysis"),
      eventPublisher: (itemKey, options) => publishZoteroEvent(itemKey, options),
    });
    zoteroUi.start();
  }
  const notifier = {
    notify(event, type, ids) {
      // The event contains only public Zotero object fields and is sent to
      // the authenticated loopback Core. It never opens zotero.sqlite.
      if (event === "add" || event === "modify") {
        Zotero.debug(`PaperFlow observed ${type}:${ids.length}`);
        if (type === "item") scheduleAnnotationMirror(ids, event);
      } else if (event === "delete" && type === "item") {
        // The annotation object may already be unavailable. Core locates the
        // existing mirror by annotation key and marks it deleted.
        scheduleAnnotationMirror(ids, "delete");
      }
    },
  };
  if (Zotero.Notifier && Zotero.Notifier.registerObserver) {
    observers.push(Zotero.Notifier.registerObserver(notifier, ["item", "tab"]));
  }
}

function shutdown() {
  for (const timer of annotationTimers.values()) clearTimeout(timer);
  annotationTimers.clear();
  for (const timer of projectionTimers.values()) clearTimeout(timer);
  projectionTimers.clear();
  if (zoteroUi) zoteroUi.stop();
  zoteroUi = null;
  if (controlCenter) controlCenter.close();
  controlCenter = null;
  readerIntegration = null;
  pluginRootURI = "";
  if (typeof Zotero !== "undefined" && Zotero.Notifier) {
    for (const id of observers.splice(0)) Zotero.Notifier.unregisterObserver(id);
  }
  removeMenuItem();
}

function install() {}
function uninstall() {}
