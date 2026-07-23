/* Public Zotero object API adapter.  This file never opens zotero.sqlite. */

"use strict";

class PaperFlowZoteroApi {
  constructor(zotero) {
    if (!zotero) throw new Error("Zotero runtime is required");
    this.Zotero = zotero;
  }

  _libraryID() {
    const id = this.Zotero.Libraries && this.Zotero.Libraries.userLibraryID;
    if (!id) throw new Error("Zotero user library is unavailable");
    return id;
  }

  async ensureCollection(name = "PaperFlow", collectionKey = "") {
    const clean = String(name || "").trim();
    if (!clean || clean.length > 200) throw new Error("Collection name is invalid");
    const libraryID = this._libraryID();
    const collections = this.Zotero.Collections;
    if (!collections) throw new Error("Zotero Collections API is unavailable");
    if (collectionKey && typeof collections.get === "function") {
      const keyed = collections.get(collectionKey);
      if (keyed && !keyed.deleted) return { status: "reused", collection: keyed, libraryID };
    }
    if (typeof collections.getByLibrary === "function") {
      const existing = collections
        .getByLibrary(libraryID)
        .find((value) => !value.deleted && String(value.name || "") === clean);
      if (existing) return { status: "reused", collection: existing, libraryID };
    }
    if (typeof this.Zotero.Collection !== "function") {
      throw new Error("Zotero Collection constructor is unavailable");
    }
    const collection = new this.Zotero.Collection();
    collection.libraryID = libraryID;
    collection.name = clean;
    if (typeof collection.saveTx !== "function") throw new Error("Zotero Collection save API is unavailable");
    await collection.saveTx();
    return { status: "created", collection, libraryID };
  }

  findItemByKey(key, libraryID = this._libraryID()) {
    if (!key || typeof this.Zotero.Items?.getByLibraryAndKey !== "function") return null;
    return this.Zotero.Items.getByLibraryAndKey(libraryID, String(key)) || null;
  }

  async getItemByKey(key, libraryID = this._libraryID()) {
    if (!key) return null;
    if (typeof this.Zotero.Items?.getAsync === "function") {
      try {
        const value = await this.Zotero.Items.getAsync(String(key));
        if (Array.isArray(value)) return value[0] || null;
        if (value) return value;
      } catch (_error) {}
    }
    return this.findItemByKey(key, libraryID);
  }

  _field(item, name) {
    if (!item || typeof item.getField !== "function") return "";
    try { return String(item.getField(name) || "").trim(); } catch (_error) { return ""; }
  }

  paperUid(item) {
    const candidates = [this._field(item, "url"), this._field(item, "extra"), this._field(item, "archiveLocation")];
    for (const value of candidates) {
      const match = value.match(/(?:arxiv(?:\.org)?\/(?:abs|pdf)\/|arXiv:)\s*([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)/i);
      if (match) return `arxiv:${match[1]}`;
    }
    const doi = this._field(item, "DOI") || this._field(item, "doi");
    if (doi) return `doi:${doi.toLowerCase()}`;
    return "";
  }

  _attachmentKeys(item) {
    if (!item || typeof item.getAttachments !== "function") return [];
    try {
      return (item.getAttachments() || []).map((value) => String(value)).filter(Boolean);
    } catch (_error) { return []; }
  }

  _inCollection(item, collectionName) {
    if (!collectionName || !item || typeof item.getCollections !== "function") return false;
    const collections = this.Zotero.Collections;
    if (!collections || typeof collections.get !== "function") return false;
    try {
      return (item.getCollections() || []).some((id) => {
        const collection = collections.get(id);
        return collection && !collection.deleted && String(collection.name || "") === collectionName;
      });
    } catch (_error) { return false; }
  }

  async eventPayload(itemKey, event = "modify", options = {}) {
    const item = await this.getItemByKey(itemKey);
    if (!item) throw new Error(`Zotero item ${itemKey} was not found`);
    const attachmentKeys = this._attachmentKeys(item);
    const isRegular = typeof item.isRegularItem === "function" ? item.isRegularItem() : !item.isAttachment?.();
    const hasPdf = attachmentKeys.length > 0;
    return {
      item_key: String(item.key || itemKey),
      event: String(event),
      item_type: String(item.itemType || "regular"),
      attachment_keys: attachmentKeys,
      timestamp: new Date().toISOString(),
      is_regular: Boolean(isRegular),
      in_collection: this._inCollection(item, options.collectionName || "PaperFlow"),
      has_pdf: hasPdf,
      // The public object API exposes attachment existence; Core will still
      // re-check the file and hash before running an analysis job.
      pdf_stable: hasPdf,
      identity_resolved: Boolean(this.paperUid(item)),
      paper_uid: this.paperUid(item),
      analysis_profile: String(options.analysisProfile || ""),
    };
  }

  async addItemToCollection(collection, item) {
    if (!collection || !item) throw new Error("Collection and item are required");
    const id = typeof item === "object" ? item.id : item;
    if (!id) throw new Error("Zotero item id is required");
    if (typeof collection.hasItem === "function" && collection.hasItem(id)) {
      return { status: "already-member", itemId: id };
    }
    if (typeof collection.addItem !== "function") throw new Error("Zotero Collection membership API is unavailable");
    await collection.addItem(id);
    return { status: "added", itemId: id };
  }

  async addItemsToCollection(collection, items) {
    const results = [];
    for (const item of items || []) results.push(await this.addItemToCollection(collection, item));
    return results;
  }

  selectedItems(win = this.Zotero.getMainWindow && this.Zotero.getMainWindow()) {
    const pane = win && win.ZoteroPane;
    if (!pane || typeof pane.getSelectedItems !== "function") return [];
    return pane.getSelectedItems().filter((item) => item && !item.isAttachment?.() && !item.isNote?.());
  }

  async ensureSelectedItemsInCollection(name = "PaperFlow") {
    const selected = this.selectedItems();
    if (!selected.length) return { status: "no-selection", added: [] };
    const ensured = await this.ensureCollection(name);
    const results = await this.addItemsToCollection(ensured.collection, selected);
    return { status: ensured.status, collectionKey: ensured.collection.key || "", added: results };
  }
}

this.PaperFlowZoteroApi = PaperFlowZoteroApi;
