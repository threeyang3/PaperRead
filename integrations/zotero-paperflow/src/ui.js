/* Public Zotero UI adapters with safe capability detection. */

"use strict";

class PaperFlowZoteroUi {
  constructor(zotero, options = {}) {
    this.Zotero = zotero;
    this.pluginID = options.pluginID || "paperflow-zotero@threeyang";
    this.rootURI = String(options.rootURI || "");
    this.notify = options.notify || (() => {});
    this.openControlCenter = options.openControlCenter || null;
    this.statusProvider = options.statusProvider || null;
    this.eventPublisher = options.eventPublisher || null;
    this.annotationProvider = options.annotationProvider || null;
    this.collectionName = options.collectionName || "PaperFlow";
    this.analysisProfile = options.analysisProfile || "";
    this.debounceMs = Math.max(250, Number(options.debounceMs || 10000));
    this.status = new Map();
    this.pending = new Map();
    this.timer = null;
    this.observerID = null;
    this.columns = [
      ["paperflow-ai", "PaperFlow AI", "ai"],
      ["paperflow-reading", "PaperFlow 阅读", "reading"],
      ["paperflow-review", "PaperFlow 复盘", "review"],
      ["paperflow-reproduction", "PaperFlow 复现", "reproduction"],
      ["paperflow-community", "PaperFlow 社区", "community"],
      ["paperflow-sync", "PaperFlow 同步", "sync"],
    ];
    this.sections = [
      ["AI 分析", [["状态", "ai"], ["模型", "analysis_model"], ["分析状态", "analysis_status"]], true],
      ["阅读", [["状态", "reading"], ["位置", "reading_position"]], true],
      ["订阅", [["状态", "subscription"], ["来源", "subscription_source"], ["更新", "subscription_update"]], false],
      ["社区", [["状态", "community"], ["贡献数", "community_count"], ["更新", "community_update"]], false],
      ["个人输出", [["复盘", "review"], ["复现", "reproduction"], ["费曼", "feynman"]], false],
      ["诊断", [["同步", "sync"], ["更新时间", "updated_at"]], false],
    ];
  }

  _value(itemKey, field) {
    const value = this.status.get(String(itemKey)) || {};
    return value[field] || "—";
  }

  _html(doc, tag) {
    return typeof doc.createElementNS === "function"
      ? doc.createElementNS("http://www.w3.org/1999/xhtml", tag)
      : doc.createElement(tag);
  }

  _ensureStyles(doc) {
    if (doc.getElementById?.("paperflow-item-pane-style")) return;
    const style = this._html(doc, "style");
    style.id = "paperflow-item-pane-style";
    style.textContent = `
      .paperflow-pane-shell{--pf-accent:#65a6ff;--pf-line:color-mix(in srgb,currentColor 16%,transparent);display:grid;gap:14px;padding:4px 2px 12px;color:inherit;font:menu}
      .paperflow-pane-intro{display:grid;gap:5px;padding:12px 13px;border:1px solid var(--pf-line);border-radius:10px;background:linear-gradient(145deg,color-mix(in srgb,var(--pf-accent) 11%,transparent),transparent 58%)}
      .paperflow-pane-kicker{font-size:10px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--pf-accent)}
      .paperflow-pane-title{font-family:"Noto Serif SC","Source Han Serif SC",serif;font-size:18px;font-weight:650;line-height:1.3}
      .paperflow-pane-subtitle{font-size:11px;line-height:1.45;opacity:.62;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .paperflow-status-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}
      .paperflow-status-cell{min-width:0;padding:9px 8px;border:1px solid var(--pf-line);border-radius:8px;background:color-mix(in srgb,currentColor 3%,transparent)}
      .paperflow-status-label{display:block;margin-bottom:3px;font-size:10px;letter-spacing:.08em;opacity:.55}
      .paperflow-status-value{display:block;font-size:12px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .paperflow-pane-sections{display:grid;gap:6px}
      .paperflow-pane-section{border:1px solid var(--pf-line);border-radius:8px;overflow:hidden}
      .paperflow-pane-section summary{padding:8px 10px;cursor:pointer;font-size:12px;font-weight:650;list-style:none}
      .paperflow-pane-section summary::-webkit-details-marker{display:none}
      .paperflow-pane-section summary::after{content:"＋";float:right;opacity:.45}
      .paperflow-pane-section[open] summary::after{content:"—"}
      .paperflow-pane-section[open] summary{border-bottom:1px solid var(--pf-line)}
      .paperflow-pane-row{display:flex;justify-content:space-between;gap:10px;padding:6px 10px;font-size:11px}
      .paperflow-pane-row-label{opacity:.55}
      .paperflow-pane-row-value{text-align:right;font-weight:600}
      .paperflow-pane-empty{padding:9px 10px;font-size:11px;opacity:.5}
      .paperflow-pane-actions{display:flex;align-items:center;gap:8px}
      .paperflow-pane-primary{appearance:none;border:0;border-radius:7px;padding:7px 11px;background:var(--pf-accent);color:#071426;font:inherit;font-size:11px;font-weight:750;cursor:pointer}
      .paperflow-pane-primary:hover{filter:brightness(1.08)}
      .paperflow-pane-hint{font-size:10px;line-height:1.4;opacity:.5}
    `;
    (doc.head || doc.documentElement).appendChild(style);
  }

  registerColumns() {
    const manager = this.Zotero && this.Zotero.ItemTreeManager;
    if (!manager || typeof manager.registerColumn !== "function") return false;
    for (const [dataKey, label, field] of this.columns) {
      try {
        manager.registerColumn({
          dataKey,
          label,
          pluginID: this.pluginID,
          enabledTreeIDs: ["main"],
          dataProvider: (item) => this._value(item && (item.key || item.id), field),
        });
      } catch (error) {
        this.Zotero.debug?.(`PaperFlow column ${dataKey} unavailable: ${error}`);
      }
    }
    return true;
  }

  unregisterColumns() {
    const manager = this.Zotero && this.Zotero.ItemTreeManager;
    if (!manager || typeof manager.unregisterColumn !== "function") return;
    for (const [dataKey] of this.columns) {
      try { manager.unregisterColumn(dataKey, this.pluginID); } catch (_error) {}
    }
  }

  registerPane() {
    const manager = this.Zotero && this.Zotero.ItemPaneManager;
    if (!manager || typeof manager.registerSection !== "function") return false;
    try {
      const win = this.Zotero?.getMainWindow?.();
      win?.MozXULElement?.insertFTLIfNeeded?.("paperflow.ftl");
      const icon = `${this.rootURI}icons/paperflow.svg`;
      manager.registerSection({
        paneID: "paperflow-item-pane",
        pluginID: this.pluginID,
        header: {
          l10nID: "paperflow-item-pane-header",
          icon,
        },
        sidenav: {
          l10nID: "paperflow-item-pane-header",
          icon,
        },
        onRender: ({ body, item }) => {
          this.renderPane(body, item);
          const key = item && (item.key || item.id);
          if (key) {
            this.refreshItem(key).then(() => this.renderPane(body, item));
          }
        },
      });
      return true;
    } catch (error) {
      this.Zotero.debug?.(`PaperFlow Item Pane unavailable: ${error}`);
      return false;
    }
  }

  renderPane(body, item) {
    if (!body || !body.ownerDocument) return;
    while (body.firstChild) body.firstChild.remove();
    const doc = body.ownerDocument;
    this._ensureStyles(doc);
    const key = item && (item.key || item.id);
    const value = this.status.get(String(key)) || {};
    const shell = this._html(doc, "div");
    shell.className = "paperflow-pane-shell";
    const intro = this._html(doc, "section");
    intro.className = "paperflow-pane-intro";
    const kicker = this._html(doc, "div");
    kicker.className = "paperflow-pane-kicker";
    kicker.textContent = "PaperFlow · Research Desk";
    const title = this._html(doc, "div");
    title.textContent = "论文工作台";
    title.className = "paperflow-pane-title";
    const subtitle = this._html(doc, "div");
    subtitle.className = "paperflow-pane-subtitle";
    subtitle.textContent = String(item?.getField?.("title") || item?.getDisplayTitle?.() || `Zotero ${key || "未选择条目"}`);
    intro.append(kicker, title, subtitle);
    shell.appendChild(intro);

    const grid = this._html(doc, "section");
    grid.className = "paperflow-status-grid";
    for (const [label, field, fallback] of [
      ["AI 分析", "ai", "待分析"],
      ["阅读", "reading", "未开始"],
      ["同步", "sync", value.linked ? "已关联" : "待关联"],
    ]) {
      const cell = this._html(doc, "div");
      cell.className = "paperflow-status-cell";
      const cellLabel = this._html(doc, "span");
      cellLabel.className = "paperflow-status-label";
      cellLabel.textContent = label;
      const cellValue = this._html(doc, "span");
      cellValue.className = "paperflow-status-value";
      cellValue.textContent = String(value[field] || fallback);
      cell.append(cellLabel, cellValue);
      grid.appendChild(cell);
    }
    shell.appendChild(grid);

    const sections = this._html(doc, "div");
    sections.className = "paperflow-pane-sections";
    for (const [label, fields, open] of this.sections) {
      const details = this._html(doc, "details");
      details.className = "paperflow-pane-section";
      details.open = Boolean(open);
      const summary = this._html(doc, "summary");
      summary.textContent = label;
      details.appendChild(summary);
      let populated = 0;
      for (const [fieldLabel, field] of fields) {
        const fieldValue = value[field];
        if (fieldValue === undefined || fieldValue === null || fieldValue === "") continue;
        const row = this._html(doc, "div");
        row.className = "paperflow-pane-row";
        const rowLabel = this._html(doc, "span");
        rowLabel.className = "paperflow-pane-row-label";
        rowLabel.textContent = fieldLabel;
        const rowValue = this._html(doc, "span");
        rowValue.className = "paperflow-pane-row-value";
        rowValue.textContent = String(fieldValue);
        row.append(rowLabel, rowValue);
        details.appendChild(row);
        populated += 1;
      }
      if (!populated) {
        const empty = this._html(doc, "div");
        empty.className = "paperflow-pane-empty";
        empty.textContent = "当前条目尚无此类记录";
        details.appendChild(empty);
      }
      sections.appendChild(details);
    }
    shell.appendChild(sections);

    const actions = this._html(doc, "div");
    actions.className = "paperflow-pane-actions";
    if (this.openControlCenter) {
      const button = this._html(doc, "button");
      button.type = "button";
      button.className = "paperflow-pane-primary";
      button.textContent = "打开控制中心";
      button.addEventListener("click", () => this.openControlCenter());
      actions.appendChild(button);
    }
    const hint = this._html(doc, "small");
    hint.className = "paperflow-pane-hint";
    hint.textContent = value.updated_at
      ? `最近更新 ${value.updated_at}`
      : `标注镜像 ${value.annotation_count ?? 0} · 等待 Core 返回条目状态`;
    actions.appendChild(hint);
    shell.appendChild(actions);
    body.appendChild(shell);
  }

  unregisterPane() {
    const manager = this.Zotero && this.Zotero.ItemPaneManager;
    if (!manager || typeof manager.unregisterSection !== "function") return;
    try { manager.unregisterSection("paperflow-item-pane", this.pluginID); } catch (_error) {}
  }

  async refreshItem(itemKey) {
    const key = String(itemKey || "");
    if (!key || !this.statusProvider) return;
    try {
      const value = await this.statusProvider(key);
      if (value && typeof value === "object") {
        const mapping = value.mapping && typeof value.mapping === "object" ? value.mapping : {};
        const state = value.status || mapping.status || (value.linked ? "已关联" : "未关联");
        this.status.set(key, {
          ...value,
          ...mapping,
          ai: value.ai || mapping.ai || (state === "complete" ? "已完成" : "—"),
          sync: value.sync || mapping.sync || (value.linked ? "已关联" : "未关联"),
          updated_at: value.updated_at || mapping.updated_at || new Date().toISOString(),
        });
        const paperUid = value.paper_uid || mapping.paper_uid || mapping.paper?.paper_uid || "";
        if (paperUid && this.annotationProvider) {
          try {
            const annotations = await this.annotationProvider(paperUid);
            const current = this.status.get(key) || {};
            this.status.set(key, { ...current, annotation_count: annotations?.active_count ?? annotations?.count ?? 0 });
          } catch (error) {
            this.Zotero.debug?.(`PaperFlow annotation status failed: ${error}`);
          }
        }
      }
      this.Zotero.ItemTreeManager?.refresh?.();
    } catch (error) {
      this.Zotero.debug?.(`PaperFlow status refresh failed: ${error}`);
    }
  }

  _schedule(keys) {
    for (const key of keys || []) {
      const normalized = String(key);
      const previous = this.status.get(normalized) || {};
      this.status.set(normalized, { ...previous, sync: "待同步", updated_at: new Date().toISOString() });
      this.pending.set(normalized, Date.now());
    }
    if (this.timer) return;
    this.timer = setTimeout(async () => {
      const keysToRefresh = [...this.pending.keys()];
      this.pending.clear();
      this.timer = null;
      for (const key of keysToRefresh) {
        if (this.eventPublisher) {
          try {
            await this.eventPublisher(key, {
              collectionName: this.collectionName,
              analysisProfile: this.analysisProfile,
            });
          } catch (error) {
            this.Zotero.debug?.(`PaperFlow Core event failed: ${error}`);
          }
        }
        await this.refreshItem(key);
      }
    }, this.debounceMs);
  }

  start() {
    this.registerColumns();
    this.registerPane();
    const notifier = {
      notify: (event, type, ids) => {
        if (["add", "modify", "delete"].includes(event) && type === "item") this._schedule(ids);
      },
    };
    if (this.Zotero?.Notifier?.registerObserver) {
      this.observerID = this.Zotero.Notifier.registerObserver(notifier, ["item"]);
    }
  }

  stop() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.pending.clear();
    if (this.observerID !== null && this.Zotero?.Notifier?.unregisterObserver) {
      this.Zotero.Notifier.unregisterObserver(this.observerID);
    }
    this.observerID = null;
    this.unregisterColumns();
    this.unregisterPane();
  }
}

globalThis.PaperFlowZoteroUi = PaperFlowZoteroUi;
