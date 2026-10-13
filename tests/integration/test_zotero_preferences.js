const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const root = path.resolve(__dirname, "../../integrations/zotero-paperflow");

function element() {
  return {
    value: "", textContent: "", disabled: false, children: [], listeners: {}, style: {},
    setAttribute(k, v) { this[k] = v; },
    addEventListener(k, fn) { this.listeners[k] = fn; },
    appendChild(child) { this.children.push(child); child.parentNode = this; },
    remove() { this.parentNode.children = this.parentNode.children.filter(x => x !== this); },
  };
}

(async () => {
  const store = new Map();
  const key = (name, global) => global ? name : `extensions.zotero.${name}`;
  const popup = element();
  const win = { document: {
    getElementById(id) { return id === "menu_ToolsPopup" ? popup : null; },
    createXULElement: element,
  } };
  const panes = [];
  const opened = [];
  let unauthorized = false;
  class Client {
    static summarizeJobs() { return { message: "暂无任务" }; }
    constructor(url, token = "", options = {}) {
      if (!url.startsWith("http://127.0.0.1:")) throw new Error("loopback required");
      this.baseUrl = url.replace(/\/$/, ""); this.token = token; this.options = options;
    }
    async health() { return { ok: true }; }
    async jobs() {
      if (unauthorized || !this.token) throw new Error("Core HTTP 401");
      return { jobs: [] };
    }
    async createPairing() { return { pairing_id: "device", pairing_secret: "local-secret" }; }
  }
  const Zotero = {
    Prefs: {
      get(name, global) { return store.get(key(name, global)); },
      set(name, value, global) { store.set(key(name, global), value); },
      clear(name, global) { store.delete(key(name, global)); },
    },
    PreferencePanes: { register(options) { panes.push(options); return Promise.resolve(options.id); } },
    Utilities: { Internal: { openPreferences(id) { opened.push(id); } } },
    getMainWindow() { return win; }, getMainWindows() { return [win]; },
  };
  const sandbox = { Zotero, PaperFlowCoreClient: Client, console, URL };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(root, "bootstrap.js"), "utf8"), sandbox);
  sandbox.startup({ rootURI: "file:///plugin/" });
  assert.equal(panes.length, 1);
  assert.equal(panes[0].src, "preferences.xhtml");
  assert.equal(panes[0].scripts[0], "src/preferences.js");
  assert.equal(popup.children.length, 1, "Tools menu exists without items or context menu");
  sandbox.addToolsMenu(win);
  assert.equal(popup.children.length, 1, "window hooks cannot duplicate menus");
  popup.children[0].children[0].children[0].listeners.command();
  assert.equal(opened[0], "paperflow-zotero-preferences");

  // Recover preferences written by older versions into the wrong branch.
  const prefix = "extensions.paperflow-zotero.";
  store.set(key(`${prefix}coreToken`, false), "legacy-token");
  assert.equal(sandbox.prefGet(`${prefix}coreToken`, ""), "legacy-token");
  sandbox.prefSet(`${prefix}coreToken`, "canonical-token");
  assert.equal(store.get(`${prefix}coreToken`), "canonical-token");
  assert.equal(store.has(key(`${prefix}coreToken`, false)), false);
  store.set(`${prefix}eventDebounceMs`, 0);
  assert.equal(sandbox.prefGet(`${prefix}eventDebounceMs`, 10000), 0);

  const fields = Object.fromEntries(["url", "token", "profile", "debounce", "status", "connect", "check", "save", "jobs"]
    .map(id => [`paperflow-prefs-${id}`, element()]));
  const doc = { getElementById(id) { return fields[id]; }, createElementNS(ns, name) {
    assert.equal(ns, "http://www.w3.org/1999/xhtml");
    const node = element(); node.tagName = name; return node;
  } };
  vm.runInContext(fs.readFileSync(path.join(root, "src/preferences.js"), "utf8"), sandbox);
  const prefs = sandbox.PaperFlowPreferences;
  const markup = fs.readFileSync(path.join(root, "preferences.xhtml"), "utf8");
  // Zotero loads pane scripts in their own sandbox; inline handlers execute
  // in the preferences window and must explicitly select that pane scope.
  const windowScope = {
    document: doc,
    Zotero_Preferences: { getScope(id) {
      assert.equal(id, "paperflow-zotero-preferences");
      return sandbox;
    } },
  };
  vm.runInNewContext(markup.match(/onload="([^"]+)"/)[1], windowScope);
  const commands = [...markup.matchAll(/oncommand="([^"]+)"/g)].map(match => match[1]);
  // Run every native button handler, not merely the underlying methods.
  // Zotero 10 exposes getScope(), not getPaneScope().
  const calls = [];
  const actionsScope = {
    Zotero_Preferences: { getScope() {
      return { PaperFlowPreferences: Object.fromEntries(
        ["connect", "check", "save", "loadJobs", "importPaper", "openControlCenter"]
          .map(name => [name, () => calls.push(name)])
      ) };
    } },
  };
  for (const command of commands) vm.runInNewContext(command, actionsScope);
  assert.deepEqual(calls, ["connect", "check", "save", "loadJobs", "importPaper", "openControlCenter"]);
  assert.equal(prefs.field("token").value, "", "never reveal saved tokens");
  prefs.field("debounce").value = "10";
  prefs.field("token").value = "valid-session-token";
  await prefs.connect();
  assert.equal(store.get(`${prefix}pairingId`), "device");
  assert.equal(prefs.field("token").value, "");
  assert.ok(prefs.field("status").textContent.includes("配对已保存"));
  assert.equal(prefs.field("connect").disabled, false);
  await prefs.check();
  assert.ok(prefs.field("status").textContent.includes("已连接"));

  prefs.renderJobs([
    { job_id: "failed1", kind: "analysis", status: "failed", error: "<script>unsafe</script>" },
    { job_id: "active1", kind: "render", status: "running" },
    { job_id: "done1", kind: "render", status: "completed" },
  ]);
  const rows = prefs.field("jobs").children;
  assert.equal(rows.length, 3);
  assert.equal(rows[0].children[1].textContent, "<script>unsafe</script>");
  assert.equal(rows[0].children[2].textContent, "按当前配置重试");
  assert.equal(rows[1].children[1].textContent, "取消任务");
  assert.equal(rows[2].children.length, 1);

  unauthorized = true;
  await prefs.check();
  assert.ok(prefs.field("status").textContent.includes("401"));
  assert.ok(!prefs.field("status").textContent.includes("已连接"), "public health is not authenticated success");
  const previousToken = store.get(`${prefix}coreToken`);
  prefs.field("token").value = "wrong-session-token";
  await prefs.connect();
  assert.equal(store.get(`${prefix}coreToken`), previousToken, "failed pairing must preserve saved configuration");
  assert.equal(prefs.field("token").value, "");

  prefs.field("url").value = "https://example.com";
  prefs.save();
  assert.ok(prefs.field("status").textContent.includes("loopback"));
  assert.equal(store.get(`${prefix}coreBaseUrl`), "http://127.0.0.1:23140");
  prefs.field("url").value = "http://127.0.0.1:23141";
  prefs.field("debounce").value = "0";
  prefs.save();
  assert.equal(store.get(`${prefix}coreBaseUrl`), "http://127.0.0.1:23140", "validate all settings before writing");
  prefs.field("debounce").value = "15";
  prefs.field("profile").value = "triage";
  prefs.save();
  assert.equal(store.get(`${prefix}coreToken`), "", "changing endpoints must discard credentials");
  assert.equal(store.get(`${prefix}pairingSecret`), "");
  assert.equal(store.get(`${prefix}eventDebounceMs`), 15000);
  assert.equal(store.get(`${prefix}analysisProfile`), "triage");

  sandbox.shutdown();
  assert.equal(popup.children.length, 0);
  assert.equal(Zotero.PaperFlowPreferences, undefined);
  console.log("PaperFlow Zotero settings and empty-library onboarding tests passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
