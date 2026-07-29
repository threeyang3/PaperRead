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
    this.coreBadge = null;
    this.activeTab = "inbox";
  }

  _window() { return this.Zotero?.getMainWindow?.() || null; }

  _html(doc, tag) {
    return typeof doc.createElementNS === "function"
      ? doc.createElementNS("http://www.w3.org/1999/xhtml", tag)
      : doc.createElement(tag);
  }

  _button(doc, label, handler) {
    const button = this._html(doc, "button");
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
    const card = this._html(doc, "section");
    card.className = "paperflow-control-card";
    const heading = this._html(doc, "h3");
    heading.textContent = title;
    const text = this._html(doc, "p");
    text.textContent = description;
    card.append(heading, text, ...buttons);
    return card;
  }

  _tab(doc, key, label, activate) {
    const tab = this._button(doc, label, () => activate(key));
    tab.className = "paperflow-control-tab";
    tab.dataset.tab = key;
    if (key === this.activeTab) tab.classList.add("is-active");
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", key === this.activeTab ? "true" : "false");
    return tab;
  }

  _panel(doc, key) {
    const panel = this._html(doc, "section");
    panel.className = "paperflow-control-panel";
    panel.dataset.tabPanel = key;
    panel.setAttribute("role", "tabpanel");
    panel.hidden = key !== this.activeTab;
    return panel;
  }

  _activateTab(key) {
    this.activeTab = key;
    if (!this.root) return;
    for (const tab of this.root.querySelectorAll?.("[data-tab]") || []) {
      const selected = tab.dataset.tab === key;
      tab.setAttribute("aria-selected", selected ? "true" : "false");
      tab.classList.toggle("is-active", selected);
    }
    for (const panel of this.root.querySelectorAll?.("[data-tab-panel]") || []) {
      panel.hidden = panel.dataset.tabPanel !== key;
    }
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
      const style = this._html(doc, "style");
      style.id = "paperflow-control-center-style";
      style.textContent = `
        .paperflow-control-center{--pf-accent:#65a6ff;--pf-line:color-mix(in srgb,currentColor 16%,transparent);box-sizing:border-box;display:block;position:fixed;right:20px;top:64px;width:520px;max-width:calc(100vw - 40px);max-height:calc(100vh - 84px);overflow:auto;z-index:2147483647;background:color-mix(in srgb,var(--material-background,Canvas) 96%,#0d1d34);color:var(--material-text-color,CanvasText);border:1px solid var(--pf-line);border-radius:14px;box-shadow:0 22px 70px #000a;font:menu;animation:paperflow-enter .18s ease-out}
        @keyframes paperflow-enter{from{opacity:0;transform:translateY(-8px) scale(.985)}to{opacity:1;transform:none}}
        .paperflow-control-center[hidden]{display:none}
        .paperflow-control-header{display:flex;justify-content:space-between;align-items:flex-start;padding:18px 20px 14px;background:linear-gradient(135deg,color-mix(in srgb,var(--pf-accent) 13%,transparent),transparent 62%);border-bottom:1px solid var(--pf-line)}
        .paperflow-control-heading{display:grid;gap:3px}
        .paperflow-control-kicker{font-size:10px;font-weight:750;letter-spacing:.15em;text-transform:uppercase;color:var(--pf-accent)}
        .paperflow-control-center h2{margin:0;font-family:"Noto Serif SC","Source Han Serif SC",serif;font-size:23px;font-weight:650;letter-spacing:.01em}
        .paperflow-control-meta{display:flex;align-items:center;gap:8px;margin-top:4px;font-size:11px;opacity:.68}
        .paperflow-core-badge{display:inline-flex;align-items:center;gap:5px}
        .paperflow-core-badge::before{content:"";width:6px;height:6px;border-radius:50%;background:#9aa0a6}
        .paperflow-control-center[data-core="online"] .paperflow-core-badge::before{background:#49c47f;box-shadow:0 0 0 3px #49c47f22}
        .paperflow-control-center[data-core="offline"] .paperflow-core-badge::before{background:#e35d6a}
        .paperflow-control-close{appearance:none;width:30px;height:30px;border:1px solid var(--pf-line);border-radius:8px;background:transparent;color:inherit;font-size:18px;line-height:1;cursor:pointer}
        .paperflow-control-close:hover{background:color-mix(in srgb,currentColor 8%,transparent)}
        .paperflow-control-tabs{display:grid;grid-template-columns:repeat(6,1fr);gap:2px;padding:9px 12px 0;border-bottom:1px solid var(--pf-line);margin:0}
        .paperflow-control-tab{appearance:none;border:0;border-bottom:2px solid transparent;background:transparent;color:inherit;padding:9px 4px 10px;white-space:nowrap;cursor:pointer;font:inherit;font-size:11px;opacity:.58}
        .paperflow-control-tab:hover{opacity:.9}
        .paperflow-control-tab.is-active{font-weight:750;opacity:1;border-bottom-color:var(--pf-accent)}
        .paperflow-control-content{padding:14px}
        .paperflow-control-panel{display:grid;gap:10px;min-height:140px}
        .paperflow-control-panel[hidden]{display:none}
        .paperflow-control-card{display:block;padding:15px;border:1px solid var(--pf-line);border-radius:10px;background:color-mix(in srgb,currentColor 3%,transparent)}
        .paperflow-control-card h3{margin:0 0 5px;font-size:14px}
        .paperflow-control-card p{margin:0 0 12px;font-size:11px;line-height:1.5;opacity:.62}
        .paperflow-control-card button{appearance:none;margin:3px 5px 3px 0;padding:7px 10px;border:1px solid var(--pf-line);border-radius:7px;background:transparent;color:inherit;font:inherit;font-size:11px;font-weight:650;cursor:pointer}
        .paperflow-control-card button:first-of-type{border-color:transparent;background:var(--pf-accent);color:#071426}
        .paperflow-control-card button:hover{filter:brightness(1.08)}
        .paperflow-reader-row{display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid var(--pf-line);font-size:11px}
        .paperflow-reader-label{opacity:.58}.paperflow-reader-value{font-weight:650;text-align:right}
        .paperflow-reader-title{margin:4px 0 8px;font-family:"Noto Serif SC","Source Han Serif SC",serif;font-size:18px}
        .paperflow-reader-summary{margin:10px 0;padding:9px 11px;border-left:3px solid var(--pf-accent);background:color-mix(in srgb,var(--pf-accent) 7%,transparent)}
        .paperflow-reader-error{color:#e35d6a;padding:8px 0}
      `;
      (doc.head || doc.documentElement).appendChild(style);
    }
    const root = this._html(doc, "aside");
    root.id = "paperflow-control-center";
    root.className = "paperflow-control-center";
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-label", "PaperFlow 控制中心");
    const header = this._html(doc, "header");
    header.className = "paperflow-control-header";
    const heading = this._html(doc, "div");
    heading.className = "paperflow-control-heading";
    const kicker = this._html(doc, "div");
    kicker.className = "paperflow-control-kicker";
    kicker.textContent = "Research Operations";
    const title = this._html(doc, "h2");
    title.textContent = "PaperFlow 控制中心";
    const meta = this._html(doc, "div");
    meta.className = "paperflow-control-meta";
    const coreBadge = this._html(doc, "span");
    coreBadge.className = "paperflow-core-badge";
    coreBadge.textContent = "正在检查 Core";
    meta.appendChild(coreBadge);
    heading.append(kicker, title, meta);
    const close = this._button(doc, "×", () => { root.hidden = true; });
    close.className = "paperflow-control-close";
    close.setAttribute("aria-label", "关闭控制中心");
    header.append(heading, close);
    root.appendChild(header);
    const tabs = this._html(doc, "nav");
    tabs.className = "paperflow-control-tabs";
    tabs.setAttribute("role", "tablist");
    const content = this._html(doc, "div");
    content.className = "paperflow-control-content";
    const selected = this.reader?.selectedItem?.();
    const panels = new Map();
    const activate = (key) => this._activateTab(key);
    for (const [key, label] of [[
      "inbox", "收件箱"
    ], [
      "analysis", "分析"
    ], [
      "reading", "阅读"
    ], [
      "subscriptions", "订阅"
    ], [
      "community", "社区"
    ], [
      "advanced", "更多"
    ]]) {
      tabs.appendChild(this._tab(doc, key, label, activate));
      panels.set(key, this._panel(doc, key));
    }
    const readerCard = this._html(doc, "section");
    readerCard.className = "paperflow-control-card paperflow-reading-workspace";
    const readerTitle = this._html(doc, "h3");
    readerTitle.textContent = "当前阅读工作区";
    const readerBody = this._html(doc, "div");
    readerBody.className = "paperflow-reader-workspace";
    readerCard.append(readerTitle, readerBody);
    this.reader?.mount?.(readerBody);
    panels.get("inbox").append(
      this._card(doc, "论文收件箱", "从 Core 导入论文，或继续处理当前选中的 Zotero 条目。", [
        this._button(doc, "从 Core 导入论文", () => this.actions.importPaper?.()),
        this._button(doc, "打开 Zotero Reader", async () => {
          const item = this.reader?.selectedItem?.();
          if (!item) return this.notify("PaperFlow：请先选择论文条目。");
          await this.reader.open(item);
          await this.reader.refresh(String(item.key || item.id));
        }),
        this._button(doc, "导入并分析", () => this.actions.analyze?.()),
      ]),
    );
    panels.get("analysis").append(
      this._card(doc, "AI 分析", "分析结果由 Core 管理；失败或待处理任务在此进入。", [
        this._button(doc, "分析当前条目", () => this.actions.analyze?.()),
        this._button(doc, "附加 AI Markdown", () => this.actions.attachAiMarkdown?.()),
        this._button(doc, "刷新分析状态", () => this.refresh()),
      ]),
    );
    panels.get("reading").append(readerCard);
    panels.get("subscriptions").append(
      this._card(doc, "订阅 Inbox", "同步可信来源并确认是否导入 Zotero。", [
        this._button(doc, "同步订阅", () => this.actions.syncSubscriptions?.()),
        this._button(doc, "查看 Inbox", () => this.actions.subscriptionInbox?.()),
      ]),
    );
    panels.get("community").append(
      this._card(doc, "社区与标注", "远程内容只读；发布个人标注前先预览。", [
        this._button(doc, "预览社区发布", () => this.actions.communityPreview?.()),
        this._button(doc, "打开社区记录", () => this.actions.communityOpen?.()),
      ]),
    );
    panels.get("advanced").append(
      this._card(doc, "诊断与设置", "低频操作和连接问题集中在这里。", [
        this._button(doc, "刷新状态", () => this.refresh()),
        this._button(doc, "连接 Core", () => this.actions.configureCore?.()),
      ]),
    );
    content.append(...panels.values());
    root.append(tabs, content);
    (doc.body || doc.documentElement).appendChild(root);
    this.root = root;
    this.coreBadge = coreBadge;
    if (selected) this.reader?.refresh?.(String(selected.key || selected.id));
    this.refresh();
    return true;
  }

  async refresh() {
    const client = this.clientProvider();
    const item = this.reader?.selectedItem?.();
    if (item && this.reader) await this.reader.refresh(String(item.key || item.id));
    if (!this.root) return;
    if (!client) {
      this.root.dataset.core = "offline";
      if (this.coreBadge) this.coreBadge.textContent = "Core 未连接";
      return;
    }
    try {
      const health = await client.health();
      this.root.dataset.core = health?.ok ? "online" : "offline";
      if (this.coreBadge) this.coreBadge.textContent = health?.ok ? "Core 已连接" : "Core 不可用";
    } catch (_error) {
      this.root.dataset.core = "offline";
      if (this.coreBadge) this.coreBadge.textContent = "Core 连接异常";
    }
  }

  close() {
    if (this.root?.parentNode) this.root.parentNode.removeChild(this.root);
    this.root = null;
    this.coreBadge = null;
  }
}

globalThis.PaperFlowControlCenter = PaperFlowControlCenter;
