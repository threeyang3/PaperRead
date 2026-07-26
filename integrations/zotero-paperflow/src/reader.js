/* Public Zotero Reader adapter. No private database or DOM assumptions. */

"use strict";

class PaperFlowReaderIntegration {
  constructor(zotero, options = {}) {
    this.Zotero = zotero;
    this.clientProvider = options.clientProvider || (() => null);
    this.notify = options.notify || (() => {});
    this.container = null;
    this.itemKey = "";
    this.state = null;
  }

  capabilities() {
    return {
      publicReader: Boolean(this.Zotero && this.Zotero.Reader),
      itemSelection: Boolean(this.Zotero?.getMainWindow?.()?.ZoteroPane?.getSelectedItems),
      itemPane: Boolean(this.Zotero?.ItemPaneManager),
    };
  }

  selectedItem() {
    const pane = this.Zotero?.getMainWindow?.()?.ZoteroPane;
    if (!pane || typeof pane.getSelectedItems !== "function") return null;
    const items = pane.getSelectedItems() || [];
    return items.find((item) => item && !item.isAttachment?.() && !item.isNote?.()) || items[0] || null;
  }

  async open(item) {
    if (!item) return { ok: false, reason: "no-selection" };
    try {
      if (this.Zotero?.Reader && typeof this.Zotero.Reader.open === "function") {
        await this.Zotero.Reader.open(item.id || item.key);
        return { ok: true, mode: "reader" };
      }
    } catch (error) {
      this.Zotero?.debug?.(`PaperFlow Reader open failed: ${error}`);
    }
    const pane = this.Zotero?.getMainWindow?.()?.ZoteroPane;
    if (pane && typeof pane.selectItem === "function") {
      pane.selectItem(item.id || item.key);
      return { ok: true, mode: "selection" };
    }
    return { ok: false, reason: "reader-api-unavailable" };
  }

  mount(container) {
    this.container = container;
    this.render();
    return this;
  }

  async refresh(itemKey) {
    const key = String(itemKey || "");
    this.itemKey = key;
    const client = this.clientProvider();
    if (!client || !key) {
      this.state = { ok: false, linked: false, diagnostics: { core: "offline" } };
      this.render();
      return this.state;
    }
    try {
      this.state = await client.itemWorkspace(key);
    } catch (error) {
      this.state = { ok: false, linked: false, error: String(error?.message || error), diagnostics: { core: "offline" } };
    }
    this.render();
    return this.state;
  }

  _text(value, fallback = "—") {
    const text = String(value ?? "").trim();
    return text || fallback;
  }

  _row(doc, label, value) {
    const row = doc.createElement("div");
    row.className = "paperflow-reader-row";
    const labelNode = doc.createElement("span");
    labelNode.className = "paperflow-reader-label";
    labelNode.textContent = label;
    const valueNode = doc.createElement("span");
    valueNode.className = "paperflow-reader-value";
    valueNode.textContent = this._text(value);
    row.append(labelNode, valueNode);
    return row;
  }

  render() {
    if (!this.container || !this.container.ownerDocument) return;
    const doc = this.container.ownerDocument;
    while (this.container.firstChild) this.container.firstChild.remove();
    const state = this.state || {};
    const paper = state.paper || {};
    const title = doc.createElement("h2");
    title.className = "paperflow-reader-title";
    title.textContent = this._text(paper.paper_title_display || paper.paper_title, "PaperFlow 阅读工作区");
    this.container.appendChild(title);
    if (paper.paper_uid) {
      const identity = doc.createElement("small");
      identity.textContent = `${paper.paper_uid}${state.item_key ? ` · Zotero ${state.item_key}` : ""}`;
      this.container.appendChild(identity);
    }
    const analysis = state.analysis || {};
    const annotations = state.annotations || {};
    const feynman = state.feynman || {};
    this.container.append(
      this._row(doc, "AI 分析", `${this._text(analysis.status)}${analysis.provider ? ` · ${analysis.provider}` : ""}`),
      this._row(doc, "标注", `${annotations.active_count ?? annotations.count ?? 0} 条有效标注`),
      this._row(doc, "费曼", `${feynman.answered_count ?? 0}/${feynman.question_count ?? 0} 已回答`),
      this._row(doc, "订阅", this._text(state.subscription?.status, "未订阅")),
      this._row(doc, "社区", `${state.community?.count ?? 0} 条贡献`),
    );
    const summary = analysis.summary?.ai_summary_short || analysis.summary?.ai_one_sentence_summary;
    if (summary) {
      const block = doc.createElement("blockquote");
      block.className = "paperflow-reader-summary";
      block.textContent = String(summary);
      this.container.appendChild(block);
    }
    if (state.error) {
      const error = doc.createElement("div");
      error.className = "paperflow-reader-error";
      error.textContent = state.error;
      this.container.appendChild(error);
    }
  }
}

this.PaperFlowReaderIntegration = PaperFlowReaderIntegration;

