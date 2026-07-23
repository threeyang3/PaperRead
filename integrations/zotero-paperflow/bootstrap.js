/* global Zotero */

"use strict";

const observers = [];
const annotationTimers = new Map();
let menuItem = null;
let collectionMenuItem = null;
let migrateMenuItem = null;
let migrationSnapshotMenuItem = null;
let connectMenuItem = null;
let analyzeMenuItem = null;
let subscriptionMenuItem = null;
let communityMenuItem = null;
let coreClient = null;
let zoteroUi = null;
let services = null;

try {
  services = ChromeUtils.importESModule("resource://gre/modules/Services.sys.mjs").Services;
} catch (_error) {
  // Older Zotero 7 builds expose Services.jsm through the legacy loader.
  try {
    services = ChromeUtils.import("resource://gre/modules/Services.jsm").Services;
  } catch (_legacyError) {}
}

function notify(message) {
  if (typeof Zotero !== "undefined" && Zotero.alert) {
    Zotero.alert(null, "PaperFlow", message);
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
  if (typeof PaperFlowCoreClient !== "undefined") return PaperFlowCoreClient;
  if (!services || typeof __SCRIPT_URI_SPEC__ === "undefined") return null;
  try {
    const uri = services.io.newURI(__SCRIPT_URI_SPEC__);
    uri.pathQueryRef = uri.pathQueryRef.replace(/bootstrap\.js(?:\?.*)?$/, "src/core-client.js");
    services.scriptloader.loadSubScript(uri.spec, globalThis);
    return typeof PaperFlowCoreClient === "undefined" ? null : PaperFlowCoreClient;
  } catch (_error) { return null; }
}

function configuredCore() {
  const Client = loadCoreClient();
  if (!Client) return null;
  try {
    return new Client(
      prefGet("extensions.paperflow-zotero.coreBaseUrl", "http://127.0.0.1:23140"),
      prefGet("extensions.paperflow-zotero.coreToken", "")
    );
  } catch (_error) { return null; }
}

async function coreStatus() {
  coreClient = configuredCore();
  if (!coreClient) {
    notify("PaperFlow Core：尚未配置会话。请使用“连接 Core”输入本机地址和一次性令牌。");
    return;
  }
  try {
    const value = await coreClient.health();
    notify(`PaperFlow Core：${value && value.ok ? "已连接" : "不可用"}`);
  } catch (error) {
    notify(`PaperFlow Core：${error.message || error}`);
  }
}

function promptValue(title, message, initial = "") {
  if (!services || !services.prompt || typeof services.prompt.prompt !== "function") return null;
  const input = { value: initial };
  const accepted = services.prompt.prompt(null, title, message, input, null, {});
  return accepted ? String(input.value || "").trim() : null;
}

async function configureCore() {
  const baseUrl = promptValue("PaperFlow Core", "请输入 loopback Core 地址：", prefGet("extensions.paperflow-zotero.coreBaseUrl", "http://127.0.0.1:23140"));
  if (baseUrl === null) return;
  const token = promptValue("PaperFlow Core", "请输入 Core 会话令牌（不会写入 Vault）：", "");
  if (token === null) return;
  try {
    const Client = loadCoreClient();
    coreClient = new Client(baseUrl, token);
    await coreClient.health();
    prefSet("extensions.paperflow-zotero.coreBaseUrl", coreClient.baseUrl);
    prefSet("extensions.paperflow-zotero.coreToken", coreClient.token);
    notify("PaperFlow Core：连接已保存到 Zotero 本机偏好设置。");
  } catch (error) {
    coreClient = null;
    notify(`PaperFlow Core：连接失败：${error.message || error}`);
  }
}

function loadZoteroApi() {
  if (typeof PaperFlowZoteroApi !== "undefined") return PaperFlowZoteroApi;
  if (!services || typeof __SCRIPT_URI_SPEC__ === "undefined") return null;
  try {
    const uri = services.io.newURI(__SCRIPT_URI_SPEC__);
    uri.pathQueryRef = uri.pathQueryRef.replace(/bootstrap\.js(?:\?.*)?$/, "src/zotero-api.js");
    services.scriptloader.loadSubScript(uri.spec, globalThis);
    return typeof PaperFlowZoteroApi === "undefined" ? null : PaperFlowZoteroApi;
  } catch (_error) {
    return null;
  }
}

function loadZoteroUi() {
  if (typeof PaperFlowZoteroUi !== "undefined") return PaperFlowZoteroUi;
  if (!services || typeof __SCRIPT_URI_SPEC__ === "undefined") return null;
  try {
    const uri = services.io.newURI(__SCRIPT_URI_SPEC__);
    uri.pathQueryRef = uri.pathQueryRef.replace(/bootstrap\.js(?:\?.*)?$/, "src/ui.js");
    services.scriptloader.loadSubScript(uri.spec, globalThis);
    return typeof PaperFlowZoteroUi === "undefined" ? null : PaperFlowZoteroUi;
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
  return coreClient.sendEvent(payload);
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
    const paperUid = api.paperUid(item);
    if (!paperUid) { skipped += 1; continue; }
    try {
      await coreClient.enqueueAnalysis({
        paper_uid: paperUid,
        zotero_item_key: String(item.key || ""),
        trigger: "zotero-manual",
        target: prefGet("extensions.paperflow-zotero.analysisTarget", "zotero"),
      });
      queued += 1;
    } catch (error) {
      Zotero.debug?.(`PaperFlow analysis enqueue failed: ${error}`);
    }
  }
  notify(`PaperFlow 分析：已排队 ${queued} 篇${skipped ? `，跳过 ${skipped} 篇（未识别 arXiv/DOI）` : ""}`);
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

async function previewCommunitySelected() {
  if (!coreClient) coreClient = configuredCore();
  const Api = loadZoteroApi();
  if (!coreClient || !Api) {
    notify("PaperFlow：请先连接 Core，再预览社区发布。");
    return;
  }
  const api = new Api(Zotero);
  const selected = api.selectedItems();
  if (!selected.length) { notify("PaperFlow：请先选择论文条目。"); return; }
  const paperUid = api.paperUid(selected[0]);
  if (!paperUid) { notify("PaperFlow：选中条目没有可验证的 arXiv/DOI 身份。"); return; }
  try {
    const result = await coreClient.communityPlan({
      paper_uid: paperUid,
      zotero_item_key: String(selected[0].key || ""),
      trigger: "zotero-menu",
    });
    notify(`PaperFlow 社区发布：${result.requires_user_confirmation ? "仅预览，待确认" : result.status || "已完成"}`);
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
  analyzeMenuItem.setAttribute("label", "PaperFlow：分析选中论文");
  analyzeMenuItem.addEventListener("command", analyzeSelectedItems);
  menu.appendChild(analyzeMenuItem);
  subscriptionMenuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  subscriptionMenuItem.id = "paperflow-zotero-sync-subscriptions";
  subscriptionMenuItem.setAttribute("label", "PaperFlow：同步订阅预览");
  subscriptionMenuItem.addEventListener("command", syncSubscriptions);
  menu.appendChild(subscriptionMenuItem);
  communityMenuItem = win.document.createXULElement
    ? win.document.createXULElement("menuitem")
    : win.document.createElement("menuitem");
  communityMenuItem.id = "paperflow-zotero-community-preview";
  communityMenuItem.setAttribute("label", "PaperFlow：社区发布预览");
  communityMenuItem.addEventListener("command", previewCommunitySelected);
  menu.appendChild(communityMenuItem);
}

function removeMenuItem() {
  if (menuItem && menuItem.parentNode) menuItem.parentNode.removeChild(menuItem);
  if (collectionMenuItem && collectionMenuItem.parentNode) collectionMenuItem.parentNode.removeChild(collectionMenuItem);
  if (migrateMenuItem && migrateMenuItem.parentNode) migrateMenuItem.parentNode.removeChild(migrateMenuItem);
  if (migrationSnapshotMenuItem && migrationSnapshotMenuItem.parentNode) migrationSnapshotMenuItem.parentNode.removeChild(migrationSnapshotMenuItem);
  if (connectMenuItem && connectMenuItem.parentNode) connectMenuItem.parentNode.removeChild(connectMenuItem);
  if (analyzeMenuItem && analyzeMenuItem.parentNode) analyzeMenuItem.parentNode.removeChild(analyzeMenuItem);
  if (subscriptionMenuItem && subscriptionMenuItem.parentNode) subscriptionMenuItem.parentNode.removeChild(subscriptionMenuItem);
  if (communityMenuItem && communityMenuItem.parentNode) communityMenuItem.parentNode.removeChild(communityMenuItem);
  menuItem = null;
  collectionMenuItem = null;
  migrateMenuItem = null;
  migrationSnapshotMenuItem = null;
  connectMenuItem = null;
  analyzeMenuItem = null;
  subscriptionMenuItem = null;
  communityMenuItem = null;
}

function startup() {
  if (typeof Zotero === "undefined") return;
  addMenuItem();
  coreClient = configuredCore();
  const Ui = loadZoteroUi();
  if (Ui) {
    zoteroUi = new Ui(Zotero, {
      pluginID: "paperflow-zotero",
      notify,
      statusProvider: (itemKey) => {
        if (!coreClient) coreClient = configuredCore();
        return coreClient ? coreClient.itemStatus(itemKey) : Promise.resolve({ linked: false, sync: "未连接 Core" });
      },
      annotationProvider: (paperUid) => {
        if (!coreClient) coreClient = configuredCore();
        return coreClient ? coreClient.annotations(paperUid) : Promise.resolve({ count: 0 });
      },
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
  if (zoteroUi) zoteroUi.stop();
  zoteroUi = null;
  if (typeof Zotero !== "undefined" && Zotero.Notifier) {
    for (const id of observers.splice(0)) Zotero.Notifier.unregisterObserver(id);
  }
  removeMenuItem();
}

function install() {}
function uninstall() {}
