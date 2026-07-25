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
let observer;
const published = [];
const fakeZotero = {
  ItemTreeManager: {
    registerColumn: (column) => columns.push(column),
    unregisterColumn: () => {},
    refresh: () => {},
  },
  ItemPaneManager: {
    registerSection: () => {},
    unregisterSection: () => {},
  },
  Notifier: {
    registerObserver: (value) => { observer = value; return 7; },
    unregisterObserver: () => {},
  },
  debug: () => {},
};

async function main() {
  const ui = new Ui(fakeZotero, {
    debounceMs: 10,
    statusProvider: async () => ({ ai: "已完成", reading: "未读", sync: "正常" }),
    eventPublisher: async (key, options) => published.push({ key, options }),
  });
  ui.start();
  assert.equal(columns.length, 5);
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
