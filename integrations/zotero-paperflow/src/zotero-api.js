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

  async getItemById(id) {
    if (!id) return null;
    if (typeof this.Zotero.Items?.getAsync === "function") {
      try {
        const value = await this.Zotero.Items.getAsync(id);
        if (Array.isArray(value)) return value[0] || null;
        if (value) return value;
      } catch (_error) {}
    }
    if (typeof this.Zotero.Items?.get === "function") {
      try { return this.Zotero.Items.get(id) || null; } catch (_error) {}
    }
    return null;
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

  _tags(item) {
    if (!item || typeof item.getTags !== "function") return [];
    try {
      return (item.getTags() || []).map((tag) => String(tag && (tag.tag || tag) || "").trim()).filter(Boolean);
    } catch (_error) { return []; }
  }

  async _sha256File(path) {
    // Zotero/Firefox exposes IOUtils and WebCrypto in modern builds.  If a
    // build does not expose them, return an empty digest and let Core mark the
    // attachment as pending verification instead of guessing.
    try {
      if (!path || typeof IOUtils === "undefined" || typeof IOUtils.read !== "function" ||
          typeof crypto === "undefined" || !crypto.subtle) return "";
      const bytes = await IOUtils.read(path);
      const digest = await crypto.subtle.digest("SHA-256", bytes);
      return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
    } catch (_error) { return ""; }
  }

  async attachmentSnapshot(item) {
    const parent = item && typeof item === "object" ? item : await this.getItemByKey(item);
    if (!parent) return [];
    const result = [];
    for (const rawKey of this._attachmentKeys(parent)) {
      const attachment = await this.getItemById(rawKey);
      if (!attachment) continue;
      let filePath = "";
      try {
        if (typeof this.Zotero.Attachments?.getFilePath === "function") {
          filePath = String(await this.Zotero.Attachments.getFilePath(attachment.id) || "");
        } else if (typeof attachment.getFilePath === "function") {
          filePath = String(await attachment.getFilePath() || "");
        }
      } catch (_error) {}
      let size = null;
      try {
        if (filePath && typeof IOUtils !== "undefined" && typeof IOUtils.stat === "function") {
          size = (await IOUtils.stat(filePath)).size || null;
        }
      } catch (_error) {}
      const linkMode = attachment.attachmentLinkMode ?? this._field(attachment, "attachmentLinkMode");
      result.push({
        key: String(attachment.key || rawKey),
        item_key: String(attachment.key || rawKey),
        content_type: this._field(attachment, "contentType"),
        filename: this._field(attachment, "title") || this._field(attachment, "filename"),
        mode: String(linkMode) === "1" ? "linked" : "stored",
        sha256: await this._sha256File(filePath),
        size,
      });
    }
    return result;
  }

  async migrationSnapshot(items = this.selectedItems(), collectionName = "PaperFlow") {
    const libraryID = this._libraryID();
    const output = [];
    for (const item of items || []) {
      if (!item || item.isAttachment?.() || item.isNote?.()) continue;
      const collections = typeof item.getCollections === "function" ? item.getCollections() || [] : [];
      output.push({
        paper_uid: this.paperUid(item),
        item_key: String(item.key || ""),
        library_id: libraryID,
        collection_keys: collections.map((value) => String(value)),
        in_collection: this._inCollection(item, collectionName),
        attachments: await this.attachmentSnapshot(item),
      });
    }
    return { schema_version: 1, library_id: libraryID, collection_name: collectionName, items: output };
  }

  _annotationField(item, name) {
    return this._field(item, name);
  }

  async annotationPayload(annotationKey, event = "modify") {
    const annotation = await this.getItemByKey(annotationKey);
    if (!annotation) {
      return event === "delete" ? { event, annotation_id: String(annotationKey), item_key: String(annotationKey), deleted: true } : null;
    }
    if (typeof annotation.isAnnotation === "function" && !annotation.isAnnotation()) return null;
    const parentID = annotation.parentID || this._annotationField(annotation, "parentItem");
    const parent = await this.getItemById(parentID);
    const paperUid = this.paperUid(parent);
    if (event !== "delete" && !paperUid) return null;
    const position = this._annotationField(annotation, "annotationPosition");
    let parsedPosition = position;
    if (position) {
      try { parsedPosition = JSON.parse(position); } catch (_error) {}
    }
    return {
      event,
      paper_uid: paperUid,
      annotation_id: String(annotation.key || annotationKey),
      item_key: String(annotation.key || annotationKey),
      parent_item_key: String(parent && parent.key || ""),
      annotation_type: this._annotationField(annotation, "annotationType"),
      text: this._annotationField(annotation, "annotationText"),
      comment: this._annotationField(annotation, "annotationComment"),
      color: this._annotationField(annotation, "annotationColor"),
      page: this._annotationField(annotation, "annotationPageLabel") || this._annotationField(annotation, "page"),
      position: parsedPosition || {},
      tags: this._tags(annotation),
      created_at: String(annotation.dateAdded || this._annotationField(annotation, "dateAdded") || ""),
      updated_at: String(annotation.dateModified || this._annotationField(annotation, "dateModified") || ""),
      deleted: event === "delete" || Boolean(annotation.deleted),
    };
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
