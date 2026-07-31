/* global fetch */

"use strict";

function normalizeLoopbackUrl(value) {
  const parsed = new URL(String(value || ""));
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error("PaperFlow Core URL must use http or https");
  }
  if (!["127.0.0.1", "localhost", "[::1]", "::1"].includes(parsed.hostname)) {
    throw new Error("PaperFlow Core must use a loopback URL");
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error("PaperFlow Core URL must not contain credentials or query data");
  }
  return `${parsed.protocol}//${parsed.host}${parsed.pathname.replace(/\/$/, "")}`;
}

class PaperFlowCoreClient {
  constructor(baseUrl = "http://127.0.0.1:23140", token = "", options = {}) {
    this.baseUrl = normalizeLoopbackUrl(baseUrl);
    this.token = "";
    this.pairingId = "";
    this.pairingSecret = "";
    this.onSession = typeof options.onSession === "function" ? options.onSession : null;
    this.setToken(token);
    this.setPairing(options.pairingId || "", options.pairingSecret || "");
  }

  setSession(baseUrl, token) {
    this.baseUrl = normalizeLoopbackUrl(baseUrl);
    this.setToken(token);
    return this;
  }

  setToken(token) {
    const value = String(token || "").trim();
    if (value && (value.length < 16 || value.length > 256 || /\s/.test(value))) {
      throw new Error("PaperFlow Core session token is invalid");
    }
    this.token = value;
    return this;
  }

  setPairing(pairingId, pairingSecret) {
    const id = String(pairingId || "").trim();
    const secret = String(pairingSecret || "").trim();
    if ((id && !secret) || (!id && secret)) {
      throw new Error("Core pairing credentials are incomplete");
    }
    if (id && (id.length > 128 || secret.length < 16 || secret.length > 256 || /\s/.test(secret))) {
      throw new Error("Core pairing credentials are invalid");
    }
    this.pairingId = id;
    this.pairingSecret = secret;
    return this;
  }

  async _fetch(method, path, { headers = {}, body, auth = true, retry = true } = {}) {
    if (auth && !this.token) {
      if (this.pairingId && this.pairingSecret) await this.refreshSession();
      else throw new Error("Core session token is not configured");
    }
    const requestHeaders = { ...headers };
    if (auth) requestHeaders.Authorization = `Bearer ${this.token}`;
    let response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: requestHeaders,
        body,
        cache: "no-store",
      });
    } catch (_error) {
      throw new Error("PaperFlow Core 不可达；请确认服务已启动且仍为本机 loopback");
    }
    if (auth && retry && response.status === 401 && this.pairingId && this.pairingSecret) {
      await this.refreshSession();
      return this._fetch(method, path, { headers, body, auth, retry: false });
    }
    return response;
  }

  async _request(method, path, body, { auth = true } = {}) {
    const headers = { Accept: "application/json" };
    let encoded;
    if (body !== undefined) {
      headers["Content-Type"] = "application/json; charset=utf-8";
      encoded = JSON.stringify(body);
    }
    const response = await this._fetch(method, path, {
      headers,
      body: encoded,
      auth,
    });
    let value = null;
    try { value = await response.json(); } catch (_error) {}
    if (!response.ok) {
      const detail = value && value.error ? `: ${value.error}` : "";
      throw new Error(`Core HTTP ${response.status}${detail}`);
    }
    return value;
  }

  health() { return this._request("GET", "/health", undefined, { auth: false }); }

  async createPairing(clientName = "PaperFlow for Zotero") {
    const value = await this._request("POST", "/zotero/pairings", {
      client_name: String(clientName || "PaperFlow for Zotero"),
    });
    this.setPairing(value?.pairing_id || "", value?.pairing_secret || "");
    return value;
  }

  async refreshSession() {
    if (!this.pairingId || !this.pairingSecret) {
      throw new Error("Core pairing is not configured");
    }
    const response = await this._fetch("POST", "/zotero/session/refresh", {
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json; charset=utf-8",
      },
      body: JSON.stringify({
        pairing_id: this.pairingId,
        pairing_secret: this.pairingSecret,
      }),
      auth: false,
      retry: false,
    });
    let value = null;
    try { value = await response.json(); } catch (_error) {}
    if (!response.ok || !value?.session_token) {
      throw new Error("Core pairing refresh failed; reconnect once to repair pairing");
    }
    this.setToken(value.session_token);
    if (this.onSession) this.onSession(this.token);
    return value;
  }

  getPaper(paperUid) {
    return this._request("GET", `/papers/${encodeURIComponent(String(paperUid || ""))}`);
  }

  async paperPdf(paperUid) {
    const response = await this._fetch(
      "GET",
      `/zotero/pdf/${encodeURIComponent(String(paperUid || ""))}`,
      { headers: { Accept: "application/pdf" } }
    );
    if (!response.ok) {
      let detail = "";
      try {
        const value = await response.json();
        detail = value?.error ? `: ${value.error}` : "";
      } catch (_error) {}
      throw new Error(`Core HTTP ${response.status}${detail}`);
    }
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length <= 5 || bytes.length > 100 * 1024 * 1024 ||
        bytes[0] !== 0x25 || bytes[1] !== 0x50 || bytes[2] !== 0x44 ||
        bytes[3] !== 0x46 || bytes[4] !== 0x2d) {
      throw new Error("Core returned an invalid PDF");
    }
    return {
      bytes,
      sha256: String(response.headers?.get?.("X-PaperFlow-Sha256") || "").toLowerCase(),
      filename: String(response.headers?.get?.("X-PaperFlow-Filename") || "paperflow-paper.pdf"),
    };
  }

  aiMarkdown(paperUid, itemKey = "") {
    const query = itemKey ? `?item_key=${encodeURIComponent(String(itemKey))}` : "";
    return this._request("GET", `/zotero/markdown/${encodeURIComponent(String(paperUid || ""))}${query}`);
  }

  itemStatus(itemKey) {
    return this._request("GET", `/zotero/items/${encodeURIComponent(String(itemKey || ""))}/status`);
  }

  itemWorkspace(itemKey) {
    return this._request("GET", `/zotero/items/${encodeURIComponent(String(itemKey || ""))}/workspace`);
  }

  annotations(paperUid) {
    return this._request("GET", `/zotero/annotations/${encodeURIComponent(String(paperUid || ""))}`);
  }

  importPaper(paper) {
    return this._request("POST", "/zotero/papers/import", { paper });
  }

  async uploadPdfChunk(paperUid, bytes, { offset = 0, total, sha256, filename = "paper.pdf", itemKey = "" } = {}) {
    if (!(bytes instanceof ArrayBuffer) && !(ArrayBuffer.isView(bytes))) {
      throw new Error("PDF chunk must be an ArrayBuffer or typed array");
    }
    const value = bytes instanceof ArrayBuffer ? bytes : bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    const headers = {
      Accept: "application/json",
      "Content-Type": "application/pdf",
      "X-PaperFlow-Offset": String(offset),
      "X-PaperFlow-Total": String(total),
      "X-PaperFlow-Sha256": String(sha256 || ""),
      "X-PaperFlow-Filename": String(filename || "paper.pdf"),
      "X-PaperFlow-Item-Key": String(itemKey || ""),
    };
    const response = await this._fetch(
      "POST",
      `/zotero/staging/${encodeURIComponent(String(paperUid || ""))}`,
      { headers, body: value }
    );
    let result = null;
    try { result = await response.json(); } catch (_error) {}
    if (!response.ok) {
      const detail = result && result.error ? `: ${result.error}` : "";
      throw new Error(`Core HTTP ${response.status}${detail}`);
    }
    return result;
  }

  mirrorAnnotation(payload) { return this._request("POST", "/zotero/annotations", payload); }

  migrationResults(payload) { return this._request("POST", "/zotero/migration/results", payload); }

  sendEvent(payload) { return this._request("POST", "/zotero/events", payload); }

  enqueueAnalysis(payload) { return this._request("POST", "/analysis/jobs", payload); }

  enqueueRender(payload) { return this._request("POST", "/render/jobs", payload); }

  syncSubscriptions(payload = {}) { return this._request("POST", "/subscriptions/sync", payload); }
  subscriptionInbox({ limit = 100, status = "" } = {}) {
    const value = Math.max(1, Math.min(500, Number(limit) || 100));
    const query = `limit=${encodeURIComponent(String(value))}${status ? `&status=${encodeURIComponent(String(status))}` : ""}`;
    return this._request("GET", `/subscriptions/inbox?${query}`);
  }
  subscriptionInboxItem(paperUid) {
    return this._request("GET", `/subscriptions/inbox/${encodeURIComponent(String(paperUid || ""))}`);
  }
  subscriptionStatus() { return this._request("GET", "/subscriptions/status"); }
  subscriptionDecision(payload) { return this._request("POST", "/subscriptions/inbox/decision", payload); }

  communityPlan(payload) { return this._request("POST", "/community/publish-plan", payload); }
  publishCommunity(payload) { return this._request("POST", "/community/publish", payload); }
  communityPaper(paperUid) {
    return this._request("GET", `/community/papers/${encodeURIComponent(String(paperUid || ""))}`);
  }

  jobs(limit = 20) {
    const value = Math.max(1, Math.min(200, Number(limit) || 20));
    return this._request("GET", `/jobs?limit=${value}`);
  }

  job(jobId) {
    return this._request("GET", `/jobs/${encodeURIComponent(String(jobId || ""))}`);
  }

  cancelJob(jobId) {
    return this._request(
      "POST",
      `/jobs/${encodeURIComponent(String(jobId || ""))}/cancel`,
      {}
    );
  }
}

// Zotero 9 loads plugin sub-scripts in a strict bootstrap sandbox. Export
// explicitly through globalThis; top-level `this` is not a reliable target in
// that environment.
globalThis.PaperFlowCoreClient = PaperFlowCoreClient;
globalThis.PaperFlowNormalizeCoreUrl = normalizeLoopbackUrl;
