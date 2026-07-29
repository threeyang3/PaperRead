"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.resolve(__dirname, "../../integrations/zotero-paperflow/src/ui.js"),
  "utf8"
);
const sandbox = { console, setTimeout, clearTimeout };
vm.runInNewContext(source, sandbox, { filename: "ui.js" });
const Ui = sandbox.PaperFlowZoteroUi;

const columns = [];
const sections = [];
const insertedFTL = [];
let observer;
const published = [];
let controlCenterOpened = 0;
const fakeZotero = {
  ItemTreeManager: {
    registerColumn: (column) => columns.push(column),
    unregisterColumn: () => {},
    refresh: () => {},
  },
  ItemPaneManager: {
    registerSection: (section) => sections.push(section),
    unregisterSection: () => {},
  },
  getMainWindow: () => ({
    MozXULElement: {
      insertFTLIfNeeded: (name) => insertedFTL.push(name),
    },
  }),
  Notifier: {
    registerObserver: (value) => { observer = value; return 7; },
    unregisterObserver: () => {},
  },
  debug: () => {},
};

async function main() {
  const ui = new Ui(fakeZotero, {
    rootURI: "resource://paperflow/",
    openControlCenter: () => { controlCenterOpened += 1; },
    debounceMs: 10,
    statusProvider: async () => ({ ai: "已完成", reading: "未读", sync: "正常" }),
    eventPublisher: async (key, options) => published.push({ key, options }),
  });
  const htmlNode = ui._html({
    createElementNS: (namespace, tag) => ({ namespace, tag }),
  }, "section");
  assert.equal(htmlNode.namespace, "http://www.w3.org/1999/xhtml");
  assert.equal(htmlNode.tag, "section");
  assert.equal(typeof ui.openControlCenter, "function");
  ui.openControlCenter();
  assert.equal(controlCenterOpened, 1);
  ui.start();
  assert.equal(columns.length, 6);
  assert.deepEqual(Array.from(columns[0].enabledTreeIDs), ["main"]);
  assert.equal(columns[0].pluginID, "paperflow-zotero@threeyang");
  assert.equal(insertedFTL[0], "paperflow.ftl");
  assert.equal(sections.length, 1);
  assert.equal(sections[0].pluginID, "paperflow-zotero@threeyang");
  assert.equal(sections[0].header.l10nID, "paperflow-item-pane-header");
  assert.equal(sections[0].header.icon, "resource://paperflow/icons/paperflow.svg");
  assert.equal(sections[0].sidenav.l10nID, "paperflow-item-pane-header");
  assert.equal(columns[0].dataProvider({ key: "A" }), "—");
  observer.notify("modify", "item", ["A"]);
  await new Promise((resolve) => setTimeout(resolve, 1100));
  assert.equal(columns[0].dataProvider({ key: "A" }), "已完成");
  assert.equal(published.length, 1);
  assert.equal(published[0].key, "A");
  ui.stop();
  console.log("PaperFlow Zotero UI adapter tests passed");
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
