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
      // Zotero 9 may return a Promise here even though older builds returned
      // an Array directly. Awaiting both shapes keeps collection reuse safe.
      const listed = await collections.getByLibrary(libraryID);
      const values = Array.isArray(listed)
        ? listed
        : listed && typeof listed[Symbol.iterator] === "function"
          ? Array.from(listed)
          : [];
      const existing = values.find(
        (value) => !value.deleted && String(value.name || "") === clean
      );
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
      // paper_uid is the stable work identity. arXiv version suffixes belong
      // in paper_arxiv_version and must never split mappings/jobs into a
      // second canonical paper such as arxiv:2504.16054v1.
      if (match) return `arxiv:${match[1].replace(/v[0-9]+$/i, "")}`;
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

  async _isPdfAttachment(rawKey) {
    const attachment = await this.getItemById(rawKey);
    if (!attachment) return false;
    const contentType = this._field(attachment, "contentType") || String(attachment.attachmentContentType || "");
    const filename = this._field(attachment, "title") || this._field(attachment, "filename") || "";
    return contentType.toLowerCase() === "application/pdf" || filename.toLowerCase().endsWith(".pdf");
  }

  async hasPdfAttachment(item) {
    const parent = item && typeof item === "object" ? item : await this.getItemByKey(item);
    if (!parent) return false;
    for (const rawKey of this._attachmentKeys(parent)) {
      if (await this._isPdfAttachment(rawKey)) return true;
    }
    return false;
  }

  _creators(item) {
    if (!item || typeof item.getCreators !== "function") return [];
    try {
      return (item.getCreators() || []).map((creator) => {
        if (!creator || typeof creator !== "object") return String(creator || "").trim();
        const first = String(creator.firstName || "").trim();
        const last = String(creator.lastName || "").trim();
        return String(creator.name || [first, last].filter(Boolean).join(" ")).trim();
      }).filter(Boolean);
    } catch (_error) { return []; }
  }

  paperSnapshot(item) {
    const paper = item && typeof item === "object" ? item : null;
    if (!paper) throw new Error("Zotero paper item is required");
    const paperUid = this.paperUid(paper);
    if (!paperUid) throw new Error("Zotero item has no verifiable arXiv/DOI identity");
    const arxivMatch = paperUid.match(/^arxiv:(.+)$/i);
    const title = this._field(paper, "title");
    if (!title) throw new Error("Zotero item has no title");
    const authors = this._creators(paper);
    const date = this._field(paper, "date");
    const yearMatch = date.match(/\b(19|20)\d{2}\b/);
    const doi = this._field(paper, "DOI") || this._field(paper, "doi");
    const url = this._field(paper, "url");
    const abstract = this._field(paper, "abstractNote");
    return {
      paper_uid: paperUid,
      paper_source: arxivMatch ? "arxiv" : "doi",
      paper_arxiv_id: arxivMatch ? arxivMatch[1].replace(/v\d+$/i, "") : "",
      paper_arxiv_version: 1,
      paper_doi: doi,
      paper_title: title,
      paper_authors: authors,
      paper_first_author: authors[0] || "",
      paper_year: yearMatch ? Number(yearMatch[0]) : null,
      paper_submitted_date: date,
      paper_abstract: abstract,
      paper_abs_url: url,
      paper_pdf_url: url && /arxiv\.org\/abs\//i.test(url) ? url.replace(/\/abs\//i, "/pdf/") + ".pdf" : "",
    };
  }

  async pdfAttachment(item) {
    const parent = item && typeof item === "object" ? item : await this.getItemByKey(item);
    if (!parent) return null;
    for (const rawKey of this._attachmentKeys(parent)) {
      const attachment = await this.getItemById(rawKey);
      if (!attachment) continue;
      const contentType = this._field(attachment, "contentType") || String(attachment.attachmentContentType || "");
      const filename = this._field(attachment, "title") || this._field(attachment, "filename") || "paper.pdf";
      if (contentType && contentType.toLowerCase() !== "application/pdf" && !filename.toLowerCase().endsWith(".pdf")) continue;
      let filePath = "";
      try {
        if (typeof this.Zotero.Attachments?.getFilePath === "function") {
          filePath = String(await this.Zotero.Attachments.getFilePath(attachment.id) || "");
        } else if (typeof attachment.getFilePath === "function") {
          filePath = String(await attachment.getFilePath() || "");
        }
      } catch (_error) {}
      if (!filePath || typeof IOUtils === "undefined" || typeof IOUtils.read !== "function") continue;
      const bytes = await IOUtils.read(filePath);
      if (!bytes || !bytes.length || bytes.length > 100 * 1024 * 1024) throw new Error("PDF attachment is empty or exceeds 100 MB");
      if (bytes[0] !== 0x25 || bytes[1] !== 0x50 || bytes[2] !== 0x44 || bytes[3] !== 0x46 || bytes[4] !== 0x2d) {
        throw new Error("Zotero attachment is not a PDF");
      }
      if (typeof crypto === "undefined" || !crypto.subtle) throw new Error("WebCrypto is required for PDF checksum verification");
      const digest = await crypto.subtle.digest("SHA-256", bytes);
      const sha256 = [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
      return { key: String(attachment.key || rawKey), filename, bytes, sha256 };
    }
    return null;
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
      let mtime = null;
      try {
        if (filePath && typeof IOUtils !== "undefined" && typeof IOUtils.stat === "function") {
          const stat = await IOUtils.stat(filePath);
          size = stat.size || null;
          mtime = Number.isFinite(Number(stat.lastModified)) ? Number(stat.lastModified) : null;
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
        mtime,
      });
    }
    return result;
  }

  async _markdownAttachments(item) {
    const parent = item && typeof item === "object" ? item : await this.getItemByKey(item);
    if (!parent) return [];
    const result = [];
    for (const rawKey of this._attachmentKeys(parent)) {
      const attachment = await this.getItemById(rawKey);
      if (!attachment) continue;
      const contentType = (this._field(attachment, "contentType") || String(attachment.attachmentContentType || "")).toLowerCase();
      const filename = this._field(attachment, "title") || this._field(attachment, "filename") || "";
      if (contentType !== "text/markdown" && !filename.toLowerCase().endsWith(".analysis.md")) continue;
      let filePath = "";
      try {
        if (typeof this.Zotero.Attachments?.getFilePath === "function") filePath = String(await this.Zotero.Attachments.getFilePath(attachment.id) || "");
        else if (typeof attachment.getFilePath === "function") filePath = String(await attachment.getFilePath() || "");
      } catch (_error) {}
      const sha256 = await this._sha256File(filePath);
      result.push({ attachment, filename, filePath, sha256 });
    }
    return result;
  }

  async _temporaryFile(bytes, filename) {
    if (typeof IOUtils === "undefined" || typeof IOUtils.write !== "function") throw new Error("Zotero 9 IOUtils.write is unavailable");
    const runtime = this.Zotero;
    let file = null;
    if (runtime && typeof runtime.getTempDirectory === "function") {
      file = runtime.getTempDirectory();
    } else if (typeof Services !== "undefined" && Services.dirsvc?.get) {
      // Zotero 9 exposes the standard Firefox directory service rather than
      // a Zotero-specific getTempDirectory helper.  Keep the file in the OS
      // temp directory and import it through Zotero's public attachment API.
      const iface = typeof Ci !== "undefined" ? Ci.nsIFile
        : (typeof Components !== "undefined" ? Components.interfaces.nsIFile : null);
      if (iface) file = Services.dirsvc.get("TmpD", iface);
    }
    if (!file) throw new Error("Zotero temporary directory API is unavailable");
    if (!file || typeof file.clone !== "function" || typeof file.append !== "function") throw new Error("Zotero temporary file API is unavailable");
    const target = file.clone();
    target.append(`paperflow-${Date.now()}-${Math.random().toString(16).slice(2)}-${filename}`);
    const value = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    await IOUtils.write(target.path, value);
    return target;
  }

  async _temporaryMarkdownFile(content, filename) {
    return this._temporaryFile(new TextEncoder().encode(String(content)), filename);
  }

  async attachStoredPdf(item, bytes, { filename = "paperflow-paper.pdf", sha256 = "" } = {}) {
    const parent = item && typeof item === "object" ? item : await this.getItemByKey(item);
    if (!parent || !parent.id) throw new Error("Zotero parent item is required");
    const value = bytes instanceof Uint8Array
      ? bytes
      : bytes instanceof ArrayBuffer
        ? new Uint8Array(bytes)
        : ArrayBuffer.isView(bytes)
          ? new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength)
          : null;
    if (!value || value.length <= 5 || value.length > 100 * 1024 * 1024 ||
        value[0] !== 0x25 || value[1] !== 0x50 || value[2] !== 0x44 ||
        value[3] !== 0x46 || value[4] !== 0x2d) {
      throw new Error("PaperFlow PDF is invalid or exceeds 100 MB");
    }
    if (typeof crypto === "undefined" || !crypto.subtle) {
      throw new Error("WebCrypto is required for PDF checksum verification");
    }
    const digest = await crypto.subtle.digest(
      "SHA-256",
      value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength)
    );
    const actual = [...new Uint8Array(digest)]
      .map((part) => part.toString(16).padStart(2, "0"))
      .join("");
    const expected = String(sha256 || "").trim().toLowerCase();
    if (expected && actual !== expected) throw new Error("PaperFlow PDF SHA-256 mismatch");
    const existing = await this.attachmentSnapshot(parent);
    if (existing.some((attachment) => attachment.sha256 && attachment.sha256 === actual)) {
      return { status: "up-to-date", attachment: null, sha256: actual };
    }
    if (!this.Zotero.Attachments || typeof this.Zotero.Attachments.importFromFile !== "function") {
      throw new Error("Zotero Attachments.importFromFile API is unavailable");
    }
    const safeName = String(filename || "paperflow-paper.pdf")
      .replace(/[^A-Za-z0-9._-]+/g, "_")
      .replace(/\.pdf$/i, "") + ".pdf";
    const temp = await this._temporaryFile(value, safeName);
    try {
      const attachment = await this.Zotero.Attachments.importFromFile({
        file: temp,
        parentItemID: parent.id,
        title: safeName,
        contentType: "application/pdf",
      });
      if (!attachment) throw new Error("Zotero did not return the imported PDF attachment");
      if (typeof attachment.setField === "function") {
        try { attachment.setField("title", safeName); } catch (_error) {}
      }
      if (typeof attachment.saveTx === "function") await attachment.saveTx();
      return { status: existing.length ? "new-version" : "created", attachment, sha256: actual };
    } finally {
      try { if (temp && typeof temp.remove === "function") temp.remove(false); } catch (_error) {}
    }
  }

  async attachAiMarkdown(item, content, { filename = "paperflow-ai.analysis.md", sha256 = "" } = {}) {
    const parent = item && typeof item === "object" ? item : await this.getItemByKey(item);
    if (!parent || !parent.id) throw new Error("Zotero parent item is required");
    const expected = String(sha256 || "").toLowerCase();
    const existing = await this._markdownAttachments(parent);
    if (expected && existing.some((value) => value.sha256 === expected)) {
      const match = existing.find((value) => value.sha256 === expected);
      return { status: "up-to-date", attachment: match.attachment, filename: match.filename, sha256: expected };
    }
    if (!this.Zotero.Attachments || typeof this.Zotero.Attachments.importFromFile !== "function") {
      throw new Error("Zotero Attachments.importFromFile API is unavailable");
    }
    const safeName = String(filename || "paperflow-ai.analysis.md").replace(/[^A-Za-z0-9._-]+/g, "_");
    const temp = await this._temporaryMarkdownFile(content, safeName);
    try {
      // Zotero 9's public signature is the options object form.  Supplying
      // content type/charset here avoids relying on filename sniffing for a
      // Markdown attachment and lets Zotero create the managed child item.
      const attachment = await this.Zotero.Attachments.importFromFile({
        file: temp,
        parentItemID: parent.id,
        title: safeName,
        contentType: "text/markdown",
        charset: "utf-8",
      });
      if (!attachment) throw new Error("Zotero did not return the imported Markdown attachment");
      if (typeof attachment.setField === "function") {
        try { attachment.setField("title", safeName); } catch (_error) {}
        // Zotero derives attachmentContentType from the imported file.  Some
        // Zotero 9 builds expose contentType as read-only, so do not make a
        // successful import fail merely because that optional field cannot be
        // assigned.
        try { attachment.setField("extra", `PaperFlow projection sha256=${expected}`); } catch (_error) {}
      }
      if (typeof attachment.saveTx === "function") await attachment.saveTx();
      return { status: existing.length ? "new-version" : "created", attachment, filename: safeName, sha256: expected };
    } finally {
      try { if (typeof temp.remove === "function") temp.remove(false); } catch (_error) {}
    }
  }

  async pdfFingerprint(item) {
    const snapshots = await this.attachmentSnapshot(item);
    const pdf = snapshots.find((value) => {
      const type = String(value.content_type || "").toLowerCase();
      const name = String(value.filename || "").toLowerCase();
      return type === "application/pdf" || name.endsWith(".pdf");
    });
    if (!pdf) return null;
    return {
      attachment_key: String(pdf.item_key || pdf.key || ""),
      size: Number.isFinite(Number(pdf.size)) ? Number(pdf.size) : null,
      mtime: Number.isFinite(Number(pdf.mtime)) ? Number(pdf.mtime) : null,
      sha256: String(pdf.sha256 || "").toLowerCase(),
    };
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
    if (!item) return "";
    // Zotero annotation data is exposed as direct Zotero.Item properties
    // (annotationText, annotationComment, annotationPosition, ...), not as
    // bibliographic fields accepted by getField(). Keep getField() only as a
    // compatibility fallback for older/mocked runtimes.
    try {
      const value = item[name];
      if (value !== undefined && value !== null) return String(value);
    } catch (_error) {}
    return this._field(item, name);
  }

  async annotationPayload(annotationKey, event = "modify") {
    const annotation = await this.getItemByKey(annotationKey);
    if (!annotation) {
      return event === "delete" ? { event, annotation_id: String(annotationKey), item_key: String(annotationKey), deleted: true } : null;
    }
    if (typeof annotation.isAnnotation === "function" && !annotation.isAnnotation()) return null;
    const parentID = annotation.parentID || this._annotationField(annotation, "parentItem");
    const attachment = await this.getItemById(parentID);
    let parent = attachment;
    if (
      attachment
      && typeof attachment.isAttachment === "function"
      && attachment.isAttachment()
      && attachment.parentID
    ) {
      parent = await this.getItemById(attachment.parentID);
    }
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

  async annotationsForItems(items = []) {
    const output = [];
    const seen = new Set();
    const add = async (value) => {
      const item = value && typeof value === "object" ? value : await this.getItemById(value);
      if (!item || typeof item.isAnnotation !== "function" || !item.isAnnotation()) return;
      const key = String(item.key || item.id || "");
      if (!key || seen.has(key)) return;
      seen.add(key);
      output.push(item);
    };
    for (const item of items || []) {
      if (!item) continue;
      if (typeof item.isAnnotation === "function" && item.isAnnotation()) {
        await add(item);
        continue;
      }
      const attachments = [];
      if (typeof item.isAttachment === "function" && item.isAttachment()) {
        attachments.push(item);
      } else if (typeof item.getAttachments === "function") {
        for (const id of item.getAttachments() || []) {
          const attachment = await this.getItemById(id);
          if (attachment) attachments.push(attachment);
        }
      }
      for (const attachment of attachments) {
        if (typeof attachment.getAnnotations !== "function") continue;
        const annotations = await attachment.getAnnotations(false, false);
        const values = Array.isArray(annotations)
          ? annotations
          : annotations && typeof annotations[Symbol.iterator] === "function"
            ? Array.from(annotations)
            : [];
        for (const annotation of values) await add(annotation);
      }
    }
    return output;
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
    const firstPdf = await this.pdfFingerprint(item);
    const secondPdf = await this.pdfFingerprint(item);
    const hasPdf = Boolean(firstPdf || secondPdf);
    const pdfStable = Boolean(
      firstPdf && secondPdf && firstPdf.sha256 && secondPdf.sha256
      && firstPdf.sha256 === secondPdf.sha256
      && (firstPdf.size === null || secondPdf.size === null || firstPdf.size === secondPdf.size)
      && (firstPdf.mtime === null || secondPdf.mtime === null || firstPdf.mtime === secondPdf.mtime)
    );
    const isRegular = typeof item.isRegularItem === "function" ? item.isRegularItem() : !item.isAttachment?.();
    return {
      item_key: String(item.key || itemKey),
      event: String(event),
      item_type: String(item.itemType || "regular"),
      attachment_keys: attachmentKeys,
      timestamp: new Date().toISOString(),
      is_regular: Boolean(isRegular),
      in_collection: this._inCollection(item, options.collectionName || "PaperFlow"),
      has_pdf: hasPdf,
      // A PDF is stable only after two public-object snapshots agree.  The
      // Core still validates the staged bytes before analysis.
      pdf_stable: pdfStable,
      pdf_sha256: secondPdf?.sha256 || firstPdf?.sha256 || "",
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
    const add = async () => collection.addItem(id);
    if (typeof this.Zotero.DB?.executeTransaction === "function") {
      // Zotero 9 enforces an active DB transaction for collection membership
      // changes even though item/collection creation use saveTx().
      await this.Zotero.DB.executeTransaction(add);
    } else {
      // Retain compatibility with test doubles and older Zotero builds whose
      // public collection API manages its own transaction.
      await add();
    }
    return { status: "added", itemId: id };
  }

  async addItemsToCollection(collection, items) {
    const results = [];
    for (const item of items || []) results.push(await this.addItemToCollection(collection, item));
    return results;
  }

  async findItemByPaperUid(paperUid) {
    const libraryID = this._libraryID();
    if (typeof this.Zotero.Items?.getAll !== "function") {
      throw new Error("Zotero item enumeration API is unavailable; refusing to risk a duplicate item");
    }
    let items;
    try {
      // Zotero 9's getAll() is asynchronous. A Promise is truthy but not
      // iterable, which previously surfaced as "items is not iterable" during
      // a confirmed Core import.
      const listed = await this.Zotero.Items.getAll(libraryID);
      items = Array.isArray(listed)
        ? listed
        : listed && typeof listed[Symbol.iterator] === "function"
          ? Array.from(listed)
          : [];
    } catch (error) {
      throw new Error(`Zotero item enumeration failed: ${error.message || error}`);
    }
    for (const item of items) {
      if (!item || item.isAttachment?.() || item.isNote?.()) continue;
      if (this.paperUid(item) === String(paperUid || "")) return item;
    }
    return null;
  }

  _creatorForZotero(value) {
    const name = String(value || "").trim();
    if (!name) return null;
    const parts = name.split(/\s+/).filter(Boolean);
    if (parts.length < 2) return { name, creatorType: "author" };
    return {
      firstName: parts.slice(0, -1).join(" "),
      lastName: parts[parts.length - 1],
      creatorType: "author",
    };
  }

  async createBibliographicItem(paper, collectionName = "PaperFlow") {
    if (!paper || typeof paper !== "object") throw new Error("PaperFlow paper snapshot is required");
    const paperUid = String(paper.paper_uid || "").trim();
    const title = String(paper.paper_title || paper.title || "").trim();
    if (!paperUid || !title) throw new Error("PaperFlow paper identity and title are required");
    const existing = await this.findItemByPaperUid(paperUid);
    const ensured = await this.ensureCollection(collectionName);
    if (existing) {
      const membership = await this.addItemToCollection(ensured.collection, existing);
      return { status: "reused", item: existing, collection: ensured, membership };
    }
    if (typeof this.Zotero.Item !== "function") throw new Error("Zotero Item constructor is unavailable");
    const item = new this.Zotero.Item("journalArticle");
    item.libraryID = this._libraryID();
    const fields = {
      title,
      abstractNote: String(paper.paper_abstract || paper.abstract || ""),
      url: String(paper.paper_abs_url || paper.url || ""),
      date: String(paper.paper_submitted_date || paper.published_at || ""),
      DOI: String(paper.paper_doi || paper.doi || ""),
      archive: paper.paper_source === "arxiv" ? "arXiv" : "",
      archiveLocation: String(paper.paper_arxiv_id || ""),
      extra: paper.paper_arxiv_id ? `arXiv:${paper.paper_arxiv_id}` : "",
    };
    for (const [field, value] of Object.entries(fields)) {
      if (!value || typeof item.setField !== "function") continue;
      item.setField(field, value);
    }
    const authors = Array.isArray(paper.paper_authors) ? paper.paper_authors : (Array.isArray(paper.authors) ? paper.authors : []);
    const creators = authors.map((value) => this._creatorForZotero(value)).filter(Boolean);
    if (creators.length && typeof item.setCreators === "function") item.setCreators(creators);
    if (typeof item.saveTx !== "function") throw new Error("Zotero Item save API is unavailable");
    await item.saveTx();
    const membership = await this.addItemToCollection(ensured.collection, item);
    return { status: "created", item, collection: ensured, membership };
  }

  selectedItems(win = this.Zotero.getMainWindow && this.Zotero.getMainWindow()) {
    const pane = win && win.ZoteroPane;
    if (!pane || typeof pane.getSelectedItems !== "function") return [];
    return pane.getSelectedItems().filter((item) => item && !item.isAttachment?.() && !item.isNote?.());
  }

  selectedAnnotations(win = this.Zotero.getMainWindow && this.Zotero.getMainWindow()) {
    return this.selectedItems(win).filter((item) => {
      try { return typeof item.isAnnotation === "function" && item.isAnnotation(); } catch (_error) { return false; }
    });
  }

  async ensureSelectedItemsInCollection(name = "PaperFlow") {
    const selected = this.selectedItems();
    if (!selected.length) return { status: "no-selection", added: [] };
    const ensured = await this.ensureCollection(name);
    const results = await this.addItemsToCollection(ensured.collection, selected);
    return { status: ensured.status, collectionKey: ensured.collection.key || "", added: results };
  }
}

globalThis.PaperFlowZoteroApi = PaperFlowZoteroApi;
