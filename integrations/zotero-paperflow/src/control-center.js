/* Lightweight Zotero-native PaperFlow control center. */

"use strict";

class PaperFlowControlCenter {
  constructor(zotero, options = {}) {
    this.Zotero = zotero;
    this.clientProvider = options.clientProvider || (() => null);
    this.reader = options.reader || null;
    this.actions = options.actions || {};
    this.notify = options.notify || (() => {});
    this.root = null;
  }

  _window() { return this.Zotero?.getMainWindow?.() || null; }

  _button(doc, label, handler) {
    const button = doc.createElement("button");
    button.type = "button";
    button.textContent = label;
    let last = 0;
    const invoke = (event) => {
      const now = Date.now();
      if (now - last < 50) return;
      last = now;
      handler(event);
    };
    button.addEventListener("command", invoke);
    button.addEventListener("click", invoke);
    return button;
  }

  _card(doc, title, description, buttons = []) {
    const card = doc.createElement("section");
    card.className = "paperflow-control-card";
    const heading = doc.createElement("h3");
    heading.textContent = title;
    const text = doc.createElement("p");
    text.textContent = description;
    card.append(heading, text, ...buttons);
    return card;
  }

  open() {
    const win = this._window();
    if (!win || !win.document) return false;
    if (this.root && this.root.isConnected) {
      this.root.hidden = false;
      this.refresh();
      return true;
    }
    const doc = win.document;
    if (!doc.getElementById("paperflow-control-center-style")) {
      const style = doc.createElement("style");
      style.id = "paperflow-control-center-style";
      style.textContent = ".paperflow-control-center{position:fixed;right:18px;top:52px;width:360px;max-height:calc(100vh - 70px);overflow:auto;z-index:2147483647;background:var(--material-background, #fff);color:var(--material-text-color, #222);border:1px solid #bbb;padding:12px;box-shadow:0 8px 30px #0004}.paperflow-control-center header{display:flex;justify-content:space-between;align-items:center}.paperflow-control-card{border-top:1px solid #ddd;padding:8px 0}.paperflow-control-card h3{margin:0 0 4px}.paperflow-control-card p{margin:0 0 6px;color:#666}.paperflow-control-card button{margin:3px 4px 3px 0}.paperflow-reader-row{display:flex;justify-content:space-between;gap:8px;padding:3px 0}.paperflow-reader-label{color:#666}.paperflow-reader-value{font-weight:600;text-align:right}.paperflow-reader-summary{margin:8px 0;padding:6px;border-left:3px solid #888}.paperflow-reader-error{color:#b00020;padding:6px 0}";
      doc.head?.appendChild(style);
    }
    const root = doc.createElement("aside");
    root.id = "paperflow-control-center";
    root.className = "paperflow-control-center";
    const header = doc.createElement("header");
    const title = doc.createElement("h2");
    title.textContent = "PaperFlow 控制中心";
    const close = this._button(doc, "关闭", () => { root.hidden = true; });
    header.append(title, close);
    root.appendChild(header);
    const content = doc.createElement("div");
    content.className = "paperflow-control-content";
    const selected = this.reader?.selectedItem?.();
    const readerCard = doc.createElement("section");
    readerCard.className = "paperflow-control-card paperflow-reading-workspace";
    const readerTitle = doc.createElement("h3");
    readerTitle.textContent = "当前阅读工作区";
    const readerBody = doc.createElement("div");
    readerBody.className = "paperflow-reader-workspace";
    readerCard.append(readerTitle, readerBody);
    this.reader?.mount?.(readerBody);
    content.append(
      this._card(doc, "论文与阅读", "导入、分析和打开当前选中的论文。", [
        this._button(doc, "打开 Zotero Reader", async () => {
          const item = this.reader?.selectedItem?.();
          if (!item) return this.notify("PaperFlow：请先选择论文条目。");
          await this.reader.open(item);
          await this.reader.refresh(String(item.key || item.id));
        }),
        this._button(doc, "导入并分析", () => this.actions.analyze?.()),
      ]),
      this._card(doc, "订阅 Inbox", "查看待确认订阅，并按需导入 Zotero。", [
        this._button(doc, "同步订阅", () => this.actions.syncSubscriptions?.()),
        this._button(doc, "查看 Inbox", () => this.actions.subscriptionInbox?.()),
      ]),
      this._card(doc, "社区与标注", "预览或确认发布选中的 Zotero 标注。", [
        this._button(doc, "预览社区发布", () => this.actions.communityPreview?.()),
        this._button(doc, "打开社区记录", () => this.actions.communityOpen?.()),
      ]),
      this._card(doc, "诊断", "检查 Core 连接、插件能力和当前条目工作区。", [
        this._button(doc, "刷新状态", () => this.refresh()),
        this._button(doc, "连接 Core", () => this.actions.configureCore?.()),
      ]),
      readerCard,
    );
    root.appendChild(content);
    doc.body.appendChild(root);
    this.root = root;
    if (selected) this.reader?.refresh?.(String(selected.key || selected.id));
    this.refresh();
    return true;
  }

  async refresh() {
    const client = this.clientProvider();
    const item = this.reader?.selectedItem?.();
    if (item && this.reader) await this.reader.refresh(String(item.key || item.id));
    if (!client || !this.root) return;
    try {
      const health = await client.health();
      this.root.dataset.core = health?.ok ? "online" : "offline";
    } catch (_error) {
      this.root.dataset.core = "offline";
    }
  }

  close() {
    if (this.root?.parentNode) this.root.parentNode.removeChild(this.root);
    this.root = null;
  }
}

this.PaperFlowControlCenter = PaperFlowControlCenter;
