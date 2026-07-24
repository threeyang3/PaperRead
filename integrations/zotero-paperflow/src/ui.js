/* Public Zotero UI adapters with safe capability detection. */

"use strict";

class PaperFlowZoteroUi {
  constructor(zotero, options = {}) {
    this.Zotero = zotero;
    this.pluginID = options.pluginID || "paperflow-zotero";
    this.notify = options.notify || (() => {});
    this.statusProvider = options.statusProvider || null;
    this.eventPublisher = options.eventPublisher || null;
    this.annotationProvider = options.annotationProvider || null;
    this.collectionName = options.collectionName || "PaperFlow";
    this.analysisProfile = options.analysisProfile || "";
    this.status = new Map();
    this.pending = new Map();
    this.timer = null;
    this.observerID = null;
    this.columns = [
      ["paperflow-ai", "PaperFlow AI", "ai"],
      ["paperflow-reading", "PaperFlow 阅读", "reading"],
      ["paperflow-review", "PaperFlow 复盘", "review"],
      ["paperflow-reproduction", "PaperFlow 复现", "reproduction"],
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

  registerColumns() {
    const manager = this.Zotero && this.Zotero.ItemTreeManager;
    if (!manager || typeof manager.registerColumn !== "function") return false;
    for (const [dataKey, label, field] of this.columns) {
      try {
        manager.registerColumn({
          dataKey,
          label,
          pluginID: this.pluginID,
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
      manager.registerSection({
        paneID: "paperflow-item-pane",
        pluginID: this.pluginID,
        header: "PaperFlow",
        onRender: ({ body, item }) => this.renderPane(body, item),
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
    const key = item && (item.key || item.id);
    const value = this.status.get(String(key)) || {};
    const title = doc.createElement("div");
    title.textContent = "PaperFlow";
    title.className = "paperflow-pane-title";
    body.appendChild(title);
    for (const [, label, field] of this.columns) {
      const row = doc.createElement("div");
      row.className = "paperflow-pane-row";
      row.textContent = `${label}：${value[field] || "—"}`;
      body.appendChild(row);
    }
    const annotationRow = doc.createElement("div");
    annotationRow.className = "paperflow-pane-row";
    annotationRow.textContent = `Zotero 标注镜像：${value.annotation_count ?? "—"}`;
    body.appendChild(annotationRow);
    for (const [label, fields, open] of this.sections) {
      const details = doc.createElement("details");
      details.className = "paperflow-pane-section";
      details.open = Boolean(open);
      const summary = doc.createElement("summary");
      summary.textContent = label;
      details.appendChild(summary);
      for (const [fieldLabel, field] of fields) {
        const row = doc.createElement("div");
        row.className = "paperflow-pane-row";
        row.textContent = `${fieldLabel}：${value[field] ?? "—"}`;
        details.appendChild(row);
      }
      body.appendChild(details);
    }
    const hint = doc.createElement("small");
    hint.textContent = value.updated_at ? `更新：${value.updated_at}` : "Core 未返回状态时显示缓存占位";
    body.appendChild(hint);
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
    }, 1000);
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

this.PaperFlowZoteroUi = PaperFlowZoteroUi;
