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
  const pdfAttachment = {
    key: "PDF00001",
    getField: (field) => field === "contentType" ? "application/pdf" : field === "title" ? "paper.pdf" : "",
  };
  const eventApi = new Api({
    Libraries: { userLibraryID: 1 },
    Items: {
      getByLibraryAndKey: () => item,
      getAsync: async (id) => id === "ABCD1234" ? item : (id === 21 || id === "21") ? pdfAttachment : annotation,
    },
    Collections: { get: () => null },
  });
  const payload = await eventApi.eventPayload("ABCD1234");
  assert.equal(payload.paper_uid, "arxiv:2504.16054v2");
  assert.equal(payload.has_pdf, true);
  assert.equal(payload.identity_resolved, true);
  assert.equal(await eventApi.hasPdfAttachment(item), true);
  const noPdf = { ...item, getAttachments: () => [22] };
  const noPdfApi = new Api({
    Libraries: { userLibraryID: 1 },
    Items: { getByLibraryAndKey: () => noPdf, getAsync: async () => ({ getField: (field) => field === "contentType" ? "text/plain" : "notes.txt" }) },
    Collections: { get: () => null },
  });
  assert.equal(await noPdfApi.hasPdfAttachment(noPdf), false);
  const annotation = {
    key: "ANN00001",
    parentID: 11,
    isAnnotation: () => true,
    getField: (field) => ({
      annotationType: "highlight",
      annotationText: "A quoted result",
      annotationComment: "Important",
      annotationColor: "#ffff00",
      annotationPageLabel: "4",
      annotationPosition: '{"rects":[[1,2,3,4]]}',
    }[field] || ""),
    getTags: () => [{ tag: "evidence" }],
  };
  const migrationSnapshot = await eventApi.migrationSnapshot([item]);
  assert.equal(migrationSnapshot.items.length, 1);
  assert.equal(migrationSnapshot.items[0].paper_uid, "arxiv:2504.16054v2");
  assert.equal(migrationSnapshot.items[0].attachments.length, 1);
  const annotationApi = new Api({
    Libraries: { userLibraryID: 1 },
    Items: {
      getByLibraryAndKey: (_library, key) => key === "ANN00001" ? annotation : null,
      getAsync: async (id) => id === 11 ? item : annotation,
    },
    Collections: { get: () => null },
  });
  const annotationPayload = await annotationApi.annotationPayload("ANN00001");
  assert.equal(annotationPayload.paper_uid, "arxiv:2504.16054v2");
  assert.equal(annotationPayload.text, "A quoted result");
  assert.equal(JSON.stringify(annotationPayload.position), JSON.stringify({ rects: [[1, 2, 3, 4]] }));
  const selectedAnnotation = { isAnnotation: () => true, key: "ANN00001" };
  const selectedApi = new Api({
    getMainWindow: () => ({ ZoteroPane: { getSelectedItems: () => [selectedAnnotation] } }),
  });
  assert.deepEqual(selectedApi.selectedAnnotations(), [selectedAnnotation]);
  const createdCalls = [];
  const createApi = new Api({
    Libraries: { userLibraryID: 1 },
    Items: { getAll: () => [] },
    Collections: {
      getByLibrary: () => [],
    },
    Collection: function Collection() {
      this.key = "PFCOLL02";
      this.name = "PaperFlow";
      this.deleted = false;
      this.saveTx = async () => createdCalls.push("collection-save");
      this.hasItem = () => false;
      this.addItem = async (id) => createdCalls.push(`collection-add:${id}`);
    },
    Item: function Item(type) {
      this.itemType = type;
      this.fields = {};
      this.setField = (field, value) => { this.fields[field] = value; };
      this.setCreators = (value) => { this.creators = value; };
      this.saveTx = async () => { this.key = "NEWITEM1"; this.id = 77; createdCalls.push("item-save"); };
      this.getCollections = () => ["PFCOLL02"];
      this.getAttachments = () => [];
      this.getField = (field) => field === "url" ? this.fields.url : field === "extra" ? this.fields.extra : field === "title" ? this.fields.title : "";
    },
  });
  const createdItem = await createApi.createBibliographicItem({
    paper_uid: "arxiv:2504.16054",
    paper_source: "arxiv",
    paper_arxiv_id: "2504.16054",
    paper_title: "π0.5",
    paper_authors: ["Physical Intelligence"],
    paper_abs_url: "https://arxiv.org/abs/2504.16054",
  });
  assert.equal(createdItem.status, "created");
  assert.equal(createdItem.item.fields.title, "π0.5");
  assert.ok(createdCalls.includes("item-save"));
  assert.ok(createdCalls.some((value) => value.startsWith("collection-add:")));
  const deletedPayload = await annotationApi.annotationPayload("ANN00001", "delete");
  assert.equal(JSON.stringify(deletedPayload), JSON.stringify({
    event: "delete",
    paper_uid: "arxiv:2504.16054v2",
    annotation_id: "ANN00001",
    item_key: "ANN00001",
    parent_item_key: "ABCD1234",
    annotation_type: "highlight",
    text: "A quoted result",
    comment: "Important",
    color: "#ffff00",
    page: "4",
    position: { rects: [[1, 2, 3, 4]] },
    tags: ["evidence"],
    created_at: "",
    updated_at: "",
    deleted: true,
  }));
  console.log("PaperFlow Zotero public API adapter tests passed");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
