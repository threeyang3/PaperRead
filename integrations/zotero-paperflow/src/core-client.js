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
  constructor(baseUrl = "http://127.0.0.1:23140", token = "") {
    this.baseUrl = normalizeLoopbackUrl(baseUrl);
    this.token = "";
    this.setToken(token);
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

  async _request(method, path, body, { auth = true } = {}) {
    if (auth && !this.token) throw new Error("Core session token is not configured");
    const headers = { Accept: "application/json" };
    if (auth) headers.Authorization = `Bearer ${this.token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json; charset=utf-8";
    let response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        cache: "no-store",
      });
    } catch (_error) {
      throw new Error("PaperFlow Core 不可达；请确认服务已启动且仍为本机 loopback");
    }
    let value = null;
    try { value = await response.json(); } catch (_error) {}
    if (!response.ok) {
      const detail = value && value.error ? `: ${value.error}` : "";
      throw new Error(`Core HTTP ${response.status}${detail}`);
    }
    return value;
  }

  health() { return this._request("GET", "/health", undefined, { auth: false }); }

  getPaper(paperUid) {
    return this._request("GET", `/papers/${encodeURIComponent(String(paperUid || ""))}`);
  }

  itemStatus(itemKey) {
    return this._request("GET", `/zotero/items/${encodeURIComponent(String(itemKey || ""))}/status`);
  }

  sendEvent(payload) { return this._request("POST", "/zotero/events", payload); }

  enqueueAnalysis(payload) { return this._request("POST", "/analysis/jobs", payload); }

  enqueueRender(payload) { return this._request("POST", "/render/jobs", payload); }

  syncSubscriptions(payload = {}) { return this._request("POST", "/subscriptions/sync", payload); }

  communityPlan(payload) { return this._request("POST", "/community/publish-plan", payload); }
}

this.PaperFlowCoreClient = PaperFlowCoreClient;
this.PaperFlowNormalizeCoreUrl = normalizeLoopbackUrl;
