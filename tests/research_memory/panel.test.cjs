"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises"), path = require("node:path"), os = require("node:os"), vm = require("node:vm");
const M = require("../../integrations/shared/research-memory/model.js");
const {Journal, NodeFiles} = require("../../integrations/shared/research-memory/storage.js");
const {mount} = require("../../integrations/shared/research-memory/panel.js");
class Node {
  constructor(tag, doc) { this.tagName = tag; this.ownerDocument = doc; this.children = []; this.events = new Map(); this.style = {}; this.value = ""; this.type = ""; this.disabled = false; this._text = ""; doc.nodes.push(this); }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text + this.children.map(n => n.textContent).join(""); }
  set innerHTML(_) { throw new Error("Unsafe HTML render"); }
  appendChild(n) { n.parentElement = this; this.children.push(n); return n; }
  append(...nodes) { nodes.forEach(n => this.appendChild(n)); }
  replaceChildren(...nodes) { this.children = []; this._text = ""; this.append(...nodes); }
  addEventListener(name, fn) { const s = this.events.get(name) || new Set(); s.add(fn); this.events.set(name, s); }
  removeEventListener(name, fn) { this.events.get(name)?.delete(fn); }
  querySelectorAll(selector) { const found = []; const visit = n => { for (const c of n.children) {
    if (selector.includes('input[type="checkbox"]') && c.tagName === "input" && c.type === "checkbox" && (!selector.endsWith(":checked") || c.checked)) found.push(c); visit(c); }}; visit(this); return found; }
  async click() { for (const fn of [...(this.events.get("click") || [])]) await fn(); }
}
class Doc { constructor() { this.nodes = []; } createElementNS(_ns, tag) { return new Node(tag, this); } }
const tick = () => new Promise(resolve => setImmediate(resolve));
async function setup(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "pf-ui-")); t.after(() => fs.rm(root, {force: true, recursive: true}));
  const journal = new Journal(new NodeFiles(root)), store = new M.Store(journal), doc = new Doc(), host = new Node("div", doc);
  const notifications = [], exports = [];
  const panel = mount(host, {store, journal, initialPaper: "arxiv:2504.16054", initialTitle: "Paper", notify: x => notifications.push(x),
    confirm: async () => true, save: async (name, text) => exports.push({name, text})});
  t.after(() => panel.close()); await tick();
  const btn = text => doc.nodes.find(n => n.tagName === "button" && n._text === text);
  const input = label => doc.nodes.find(n => n.tagName === "label" && n._text === label).children[0];
  return {doc, host, panel, journal, store, btn, input, notifications, exports};
}
test("panel completes actual manual browser question -> answer -> private export", async t => {
  const f = await setup(t);
  await f.btn("建立会话").click();
  f.input("问题（每次调用只包含此问题和勾选材料；历史对话不会隐式全量发送）").value = "Explain this result";
  await f.btn("导出浏览器提问包").click(); assert.equal(f.exports.length, 1);
  const pack = JSON.parse(f.exports[0].text);
  f.input("回传 / 私有会话 JSON（粘贴文件内容）").value = JSON.stringify({...pack.reply_contract, content: "<script>not executed</script>"});
  await f.btn("导入浏览器回答").click();
  await f.btn("导出私有会话 JSON").click();
  const exported = JSON.parse(f.exports.at(-1).text);
  assert.equal(exported.conversation.messages.length, 2);
  assert.equal(exported.conversation.messages.at(-1).content, "<script>not executed</script>");
  assert.deepEqual(f.notifications, []);
});
test("panel close clears credential, events and rendered records", async t => {
  const f = await setup(t); const key = f.input("API Key（不写入本地配置或会话）"); key.value = "do-not-persist";
  await f.btn("建立会话").click(); f.panel.close();
  assert.equal(key.value, ""); assert.equal(f.host.children.length, 0);
  assert(f.doc.nodes.every(n => [...n.events.values()].every(set => set.size === 0)));
  const r = (await f.journal.list()).items[0]; assert(!M.encode(await f.store.read(r.id)).includes("do-not-persist"));
});
test("panel rerender releases obsolete click listeners", async t => {
  const f = await setup(t); await f.btn("建立会话").click();
  f.input("问题（每次调用只包含此问题和勾选材料；历史对话不会隐式全量发送）").value = "q";
  await f.btn("导出浏览器提问包").click();
  const old = f.doc.nodes.filter(n => n.tagName === "button" && n._text === "取消未完成任务");
  await f.btn("刷新（冲突后重读）").click();
  assert(old.every(n => (n.events.get("click")?.size || 0) === 0));
});
test("shared scripts load in a Zotero-style sandbox without CommonJS", async () => {
  const sandbox = {crypto, TextEncoder, TextDecoder, URL, AbortController, setTimeout, clearTimeout}; vm.createContext(sandbox);
  for (const name of ["model", "storage", "client", "panel"]) {
    vm.runInContext(await fs.readFile(path.resolve(__dirname, `../../integrations/zotero-paperflow/research-memory/${name}.js`), "utf8"), sandbox);
  }
  assert.equal(typeof sandbox.PaperFlowResearchModel.Store, "function");
  assert.equal(typeof sandbox.PaperFlowResearchPanel.mount, "function");
  assert.equal(typeof sandbox.PaperFlowResearchStorage.MozillaFiles, "function");
});
test("both host entries are wired and no shell/native debugger/third-party connector is imported", async () => {
  const root = path.resolve(__dirname, "../../integrations");
  const ob = await fs.readFile(path.join(root, "obsidian-paperflow-automation/main.js"), "utf8");
  const zo = await fs.readFile(path.join(root, "zotero-paperflow/bootstrap.js"), "utf8");
  assert(ob.includes('require("./research.js").open(this)')); assert(zo.includes('research-memory/${name}.js'));
  for (const name of ["model", "storage", "client", "panel"]) {
    const text = await fs.readFile(path.join(root, `shared/research-memory/${name}.js`), "utf8");
    assert(!/child_process|chrome\.debugger|GM_xmlhttpRequest|document\.cookie|eval\(/.test(text));
  }
});
