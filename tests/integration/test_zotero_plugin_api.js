"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.resolve(__dirname, "../../integrations/zotero-paperflow/src/zotero-api.js"),
  "utf8"
);
const sandbox = { console };
vm.runInNewContext(source, sandbox, { filename: "zotero-api.js" });
const Api = sandbox.PaperFlowZoteroApi;

async function main() {
  const saved = [];
  const collection = {
    key: "PFCOLL01",
    name: "PaperFlow",
    deleted: false,
    saveTx: async () => saved.push("save"),
    addItem: async (id) => saved.push(`add:${id}`),
    hasItem: () => false
  };
  const Zotero = {
    Libraries: { userLibraryID: 1 },
    Collections: { getByLibrary: () => [] },
    Collection: function Collection() {
      this.key = "PFCOLL01";
      this.saveTx = async () => saved.push("save");
      this.addItem = async (id) => saved.push(`add:${id}`);
      this.hasItem = () => false;
    },
    Items: { getByLibraryAndKey: (_library, key) => ({ id: 5, key }) }
  };
  const api = new Api(Zotero);
  const created = await api.ensureCollection();
  assert.equal(created.status, "created");
  assert.equal(created.libraryID, 1);
  assert.deepEqual(saved, ["save"]);
  const added = await api.addItemToCollection(collection, { id: 9, key: "ITEM0001" });
  assert.equal(added.status, "added");
  collection.hasItem = () => true;
  const existing = await api.addItemToCollection(collection, { id: 9, key: "ITEM0001" });
  assert.equal(existing.status, "already-member");
  assert.equal(api.findItemByKey("ITEM0001").key, "ITEM0001");
  const item = {
    key: "ABCD1234",
    itemType: "journalArticle",
    isRegularItem: () => true,
    getField: (field) => field === "url" ? "https://arxiv.org/abs/2504.16054v2" : "",
    getAttachments: () => [21],
    getCollections: () => [],
  };
  const eventApi = new Api({
    Libraries: { userLibraryID: 1 },
    Items: { getByLibraryAndKey: () => item },
    Collections: { get: () => null },
  });
  const payload = await eventApi.eventPayload("ABCD1234");
  assert.equal(payload.paper_uid, "arxiv:2504.16054v2");
  assert.equal(payload.has_pdf, true);
  assert.equal(payload.identity_resolved, true);
  console.log("PaperFlow Zotero public API adapter tests passed");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
