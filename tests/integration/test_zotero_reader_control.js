"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function load(file, name) {
  const sandbox = { console, setTimeout, clearTimeout };
  vm.runInNewContext(fs.readFileSync(path.resolve(__dirname, file), "utf8"), sandbox, { filename: name });
  return sandbox;
}

async function main() {
  const readerSandbox = load("../../integrations/zotero-paperflow/src/reader.js", "reader.js");
  const controlSandbox = load("../../integrations/zotero-paperflow/src/control-center.js", "control-center.js");
  const selected = { key: "ITEM0001", id: 11, isAttachment: () => false, isNote: () => false };
  const zotero = {
    Reader: { open: async () => {} },
    getMainWindow: () => ({ ZoteroPane: { getSelectedItems: () => [selected], selectItem: () => {} } }),
  };
  const reader = new readerSandbox.PaperFlowReaderIntegration(zotero, {
    clientProvider: () => ({
      itemWorkspace: async () => ({ ok: true, item_key: "ITEM0001", paper: { paper_uid: "arxiv:2504.16054", paper_title_display: "π₀.₅" }, analysis: { status: "complete" } }),
    }),
  });
  assert.equal(JSON.stringify(reader.capabilities()), JSON.stringify({ publicReader: true, itemSelection: true, itemPane: false }));
  assert.equal(reader.selectedItem(), selected);
  assert.equal(JSON.stringify(await reader.open(selected)), JSON.stringify({ ok: true, mode: "reader" }));
  const state = await reader.refresh("ITEM0001");
  assert.equal(state.paper.paper_title_display, "π₀.₅");
  reader.render(); // Safe no-op without a DOM container.

  const fallback = new readerSandbox.PaperFlowReaderIntegration({
    getMainWindow: () => ({ ZoteroPane: { getSelectedItems: () => [selected], selectItem: () => {} } }),
  });
  assert.equal(JSON.stringify(await fallback.open(selected)), JSON.stringify({ ok: true, mode: "selection" }));

  const control = new controlSandbox.PaperFlowControlCenter(zotero, { reader });
  assert.equal(control.open(), false, "control center must safely no-op without a Zotero DOM");
  control.close();
  const source = fs.readFileSync(path.resolve(__dirname, "../../integrations/zotero-paperflow/src/control-center.js"), "utf8");
  for (const label of ["论文与阅读", "订阅 Inbox", "社区与标注", "诊断", "当前阅读工作区"]) assert.ok(source.includes(label));
  console.log("PaperFlow Zotero Reader/control-center tests passed");
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
