/* PaperFlow Research Memory. Shared, host-independent, data-only model. MIT. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PaperFlowResearchModel = api;
})(globalThis, function () {
  "use strict";
  const VERSION = 1;
  const LIMITS = Object.freeze({bytes: 4 * 1024 * 1024, messages: 500, contexts: 100,
    requests: 250, insights: 200, text: 100000, papers: 20});
  class ConflictError extends Error { constructor(message) { super(message); this.name = "ConflictError"; } }
  function assert(ok, message) { if (!ok) throw new Error(message); }
  function object(value, label) {
    assert(value && typeof value === "object" && !Array.isArray(value), `${label}: expected object`);
    return value;
  }
  function string(value, label, max = 1000, empty = false) {
    assert(typeof value === "string" && value.length <= max && (empty || value.trim())
      && !/[\u0000\u0008\u000b\u000c]/.test(value), `${label}: invalid text`);
    return value;
  }
  function id(value) { assert(typeof value === "string" && /^[a-f0-9]{32}$/.test(value), "invalid record ID"); return value; }
  function uid(value) {
    string(value, "paper_uid", 300);
    const canonical = value.trim().toLowerCase();
    assert(/^(?:arxiv:\d{4}\.\d{4,5}|doi:10\.\d{4,9}\/[^\s]+)$/.test(canonical), "invalid canonical paper_uid");
    return canonical;
  }
  function hash(value) { assert(typeof value === "string" && /^[a-f0-9]{64}$/.test(value), "invalid SHA-256"); return value; }
  function list(value, label, max) { assert(Array.isArray(value) && value.length <= max, `${label}: invalid list`); return value; }
  function unique(values) { return [...new Set(values)]; }
  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function encode(value) {
    const result = JSON.stringify(value);
    assert(new TextEncoder().encode(result).length <= LIMITS.bytes, "record exceeds 4 MiB");
    return result;
  }
  function parse(value) {
    string(value, "JSON", LIMITS.bytes);
    assert(new TextEncoder().encode(value).length <= LIMITS.bytes, "record exceeds 4 MiB");
    return JSON.parse(value, (key, item) => {
      assert(!["__proto__", "prototype", "constructor"].includes(key), "unsafe JSON key");
      return item;
    });
  }
  function strict(value, allowed, label) {
    object(value, label);
    for (const key of Object.keys(value)) assert(allowed.includes(key), `${label}: unsupported field ${key}`);
    return value;
  }
  const token = () => {
    assert(globalThis.crypto?.getRandomValues, "WebCrypto is required");
    return Array.from(globalThis.crypto.getRandomValues(new Uint8Array(16)), x => x.toString(16).padStart(2, "0")).join("");
  };
  async function digest(text) {
    assert(globalThis.crypto?.subtle, "WebCrypto is required");
    const bytes = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(bytes), x => x.toString(16).padStart(2, "0")).join("");
  }
  const now = () => new Date().toISOString();
  const byID = (items, target, label) => {
    const result = items.find(x => x.id === id(target));
    assert(result, `${label} not found`); return result;
  };
  function refs(record, values, collection) {
    list(values, collection, 100);
    assert(unique(values).length === values.length, `duplicate ${collection} reference`);
    for (const key of values) byID(record[collection], key, collection);
    return [...values];
  }
  function endpoint(value) {
    const url = new URL(string(value, "API endpoint", 2048));
    assert(url.protocol === "https:" && !url.username && !url.password && !url.search && !url.hash,
      "API endpoint must be HTTPS without credentials, query or fragment");
    return url.href.replace(/\/$/, "");
  }
  // Local integrity is not evidence of a trustworthy AI answer.
  async function validate(record) {
    strict(record, ["schema_version", "id", "revision", "paper_uids", "title", "created_at", "updated_at",
      "contexts", "messages", "requests", "insights", "import_sha256"], "record");
    assert(record.schema_version === VERSION, "unsupported schema_version"); id(record.id);
    assert(Number.isSafeInteger(record.revision) && record.revision >= 0, "invalid revision");
    string(record.title, "title", 500); string(record.created_at, "created_at"); string(record.updated_at, "updated_at");
    list(record.paper_uids, "papers", LIMITS.papers);
    assert(record.paper_uids.length > 0 && unique(record.paper_uids).length === record.paper_uids.length, "invalid papers");
    record.paper_uids.forEach(v => assert(uid(v) === v, "noncanonical paper identity"));
    for (const field of ["contexts", "messages", "requests", "insights"]) {
      list(record[field], field, LIMITS[field]);
      assert(unique(record[field].map(x => id(x.id))).length === record[field].length, `duplicate ${field} ID`);
    }
    for (const c of record.contexts) {
      strict(c, ["id", "paper_uid", "kind", "text", "sha256", "version", "locator"], "context");
      assert(record.paper_uids.includes(uid(c.paper_uid)), "context outside paper scope");
      assert(["abstract", "excerpt", "user-note"].includes(c.kind), "unsupported context kind");
      string(c.text, "context text", LIMITS.text); string(c.version, "version", 100, true);
      string(c.locator, "locator", 500, true); hash(c.sha256);
      assert(await digest(c.text) === c.sha256, "context checksum mismatch");
    }
    for (const m of record.messages) {
      strict(m, ["id", "role", "content", "context_ids", "created_at", "source", "status", "request_id"], "message");
      assert(["user", "assistant"].includes(m.role), "invalid message role");
      string(m.content, "message", LIMITS.text); string(m.created_at, "message date");
      refs(record, m.context_ids, "contexts");
      assert(["manual", "api", "browser", "import"].includes(m.source), "invalid message source");
      assert(["complete", "partial", "imported-unverified"].includes(m.status), "invalid message status");
      if (m.request_id) id(m.request_id);
    }
    for (const q of record.requests) {
      strict(q, ["id", "message_id", "prompt_sha256", "context_ids", "provider", "model", "state",
        "created_at", "reply_sha256", "response_message_id"], "request");
      const m = byID(record.messages, q.message_id, "prompt");
      assert(m.role === "user", "request prompt must be user message");
      refs(record, q.context_ids, "contexts");
      assert(JSON.stringify(q.context_ids) === JSON.stringify(m.context_ids), "request context mismatch");
      assert(await digest(m.content) === hash(q.prompt_sha256), "prompt checksum mismatch");
      assert(["pending", "complete", "partial", "cancelled", "failed"].includes(q.state), "invalid request state");
      string(q.provider, "provider", 80); string(q.model, "model", 200, true); string(q.created_at, "request date");
      if (q.reply_sha256) hash(q.reply_sha256);
      if (q.response_message_id) byID(record.messages, q.response_message_id, "response");
    }
    for (const i of record.insights) {
      strict(i, ["id", "claim", "kind", "message_ids", "evidence", "review", "publication_text", "created_at"], "insight");
      string(i.claim, "claim", 12000); string(i.created_at, "insight date");
      assert(["paper-claim", "interpretation", "hypothesis", "question"].includes(i.kind), "invalid insight kind");
      assert(i.message_ids.length > 0, "insight requires source messages"); refs(record, i.message_ids, "messages");
      assert(["candidate", "accepted", "rejected"].includes(i.review), "invalid review state");
      list(i.evidence, "evidence", 30);
      const permitted = new Set(i.message_ids.flatMap(mid => byID(record.messages, mid, "message").context_ids));
      for (const e of i.evidence) {
        strict(e, ["context_id", "quote", "match"], "evidence");
        const context = byID(record.contexts, e.context_id, "context");
        assert(permitted.has(e.context_id), "evidence was not supplied to the source message");
        assert(i.kind !== "paper-claim" || context.kind !== "user-note", "personal notes are not paper evidence");
        string(e.quote, "quote", 10000);
        assert(e.match === "quote-matched" && context.text.includes(e.quote), "quote does not match supplied source");
      }
      string(i.publication_text, "publication text", 12000, true);
      assert(!i.publication_text || i.review === "accepted", "unaccepted insight cannot be published");
    }
    if (record.import_sha256) hash(record.import_sha256);
    encode(record); return record;
  }
  class Store {
    // io.load(id) -> latest snapshot or null. io.commit(id, expected, record)
    // must atomically publish revision expected+1 with no-overwrite semantics.
    constructor(io) { this.io = io; }
    async read(key) {
      const result = await this.io.load(id(key));
      return result ? clone(await validate(result)) : null;
    }
    async change(key, expected, fn) {
      const current = await this.read(key); assert(current, "conversation not found");
      if (current.revision !== expected) throw new ConflictError("Conversation changed; reload before writing");
      const updated = clone(current);
      const result = await fn(updated);
      if (result?.unchanged) return {record: current, result};
      updated.revision++; updated.updated_at = now();
      await validate(updated); await this.io.commit(key, expected, updated);
      return {record: updated, result};
    }
    async create(papers, title) {
      const record = {schema_version: VERSION, id: token(), revision: 1,
        paper_uids: unique(papers.map(uid)), title, created_at: now(), updated_at: now(),
        contexts: [], messages: [], requests: [], insights: [], import_sha256: ""};
      await validate(record); await this.io.commit(record.id, 0, record); return clone(record);
    }
    async context(key, revision, input) {
      strict(input, ["paper_uid", "kind", "text", "version", "locator"], "new context");
      return this.change(key, revision, async r => {
        const context = {id: token(), paper_uid: uid(input.paper_uid), kind: input.kind,
          text: input.text, sha256: await digest(input.text), version: input.version || "", locator: input.locator || ""};
        r.contexts.push(context); return {context_id: context.id};
      });
    }
    async message(key, revision, input) {
      strict(input, ["role", "content", "context_ids"], "new message");
      return this.change(key, revision, r => {
        const m = {id: token(), role: input.role, content: input.content,
          context_ids: refs(r, input.context_ids || [], "contexts"), created_at: now(), source: "manual", status: "complete", request_id: ""};
        r.messages.push(m); return {message_id: m.id};
      });
    }
    async request(key, revision, input) {
      strict(input, ["question", "context_ids", "provider", "model"], "new request");
      return this.change(key, revision, async r => {
        const context_ids = refs(r, input.context_ids || [], "contexts");
        const qid = token();
        const m = {id: token(), role: "user", content: input.question, context_ids,
          created_at: now(), source: "manual", status: "complete", request_id: qid};
        const request = {id: qid, message_id: m.id, prompt_sha256: await digest(input.question), context_ids,
          provider: input.provider, model: input.model || "", state: "pending", created_at: now(), reply_sha256: "", response_message_id: ""};
        r.messages.push(m); r.requests.push(request); return {request_id: qid};
      });
    }
    async requestPack(key, request_id) {
      const r = await this.read(key); assert(r, "conversation not found");
      const q = byID(r.requests, request_id, "request"); assert(q.state === "pending", "request is no longer pending");
      return {schema_version: VERSION, kind: "paperflow-question", conversation_id: r.id,
        request_id: q.id, prompt_sha256: q.prompt_sha256, provider: q.provider, model: q.model,
        question: byID(r.messages, q.message_id, "prompt").content,
        contexts: q.context_ids.map(key => clone(byID(r.contexts, key, "context"))),
        reply_contract: {kind: "paperflow-answer", schema_version: VERSION, conversation_id: r.id,
          request_id: q.id, prompt_sha256: q.prompt_sha256, provider: q.provider,
          content: "REPLACE_WITH_VISIBLE_ANSWER", completion: "complete"}};
    }
    async reply(key, revision, input) {
      strict(input, ["schema_version", "kind", "conversation_id", "request_id", "prompt_sha256", "provider", "content", "completion"], "reply");
      assert(input.schema_version === VERSION && input.kind === "paperflow-answer" && input.conversation_id === key, "reply belongs to another conversation");
      string(input.content, "reply text", LIMITS.text);
      assert(["complete", "partial"].includes(input.completion), "unknown completion state");
      return this.change(key, revision, async r => {
        const q = byID(r.requests, input.request_id, "request");
        assert(input.prompt_sha256 === q.prompt_sha256 && input.provider === q.provider, "reply request binding mismatch");
        const signature = await digest(encode(input));
        if (q.reply_sha256 === signature) return {unchanged: true, message_id: q.response_message_id};
        assert(q.state === "pending", "request is terminal; create a new request, do not overwrite the answer");
        const m = {id: token(), role: "assistant", content: input.content, context_ids: [...q.context_ids],
          created_at: now(), source: q.provider === "browser" ? "browser" : "api", status: input.completion, request_id: q.id};
        r.messages.push(m); q.state = input.completion; q.reply_sha256 = signature; q.response_message_id = m.id;
        return {message_id: m.id};
      });
    }
    async stop(key, revision, request_id, state = "cancelled") {
      assert(["cancelled", "failed"].includes(state), "invalid stop state");
      return this.change(key, revision, r => {
        const q = byID(r.requests, request_id, "request");
        if (q.state === state) return {unchanged: true};
        assert(q.state === "pending", "request already terminal"); q.state = state;
      });
    }
    async propose(key, revision, candidates) {
      list(candidates, "candidates", 30);
      return this.change(key, revision, r => {
        const added = [];
        for (const c of candidates) {
          // Model output never carries review/approval/publication capabilities.
          strict(c, ["claim", "kind", "message_ids", "evidence"], "candidate");
          refs(r, c.message_ids, "messages");
          assert(c.message_ids.every(mid => byID(r.messages, mid, "message").status !== "partial"), "partial answers cannot be distilled");
          const comparable = JSON.stringify([c.claim, c.kind, [...c.message_ids].sort()]);
          const duplicate = r.insights.find(i => JSON.stringify([i.claim, i.kind, [...i.message_ids].sort()]) === comparable);
          if (duplicate) { added.push(duplicate.id); continue; }
          const item = {id: token(), claim: c.claim, kind: c.kind, message_ids: [...c.message_ids],
            evidence: (c.evidence || []).map(e => { strict(e, ["context_id", "quote"], "candidate evidence");
              return {...e, match: "quote-matched"}; }), review: "candidate", publication_text: "", created_at: now()};
          r.insights.push(item); added.push(item.id);
        }
        return {insight_ids: added};
      });
    }
    async review(key, revision, insight_id, decision, confirmed) {
      assert(confirmed === true && ["accepted", "rejected", "candidate"].includes(decision), "explicit human review is required");
      return this.change(key, revision, r => {
        const i = byID(r.insights, insight_id, "insight");
        assert(decision !== "accepted" || i.kind !== "paper-claim" || i.evidence.length > 0,
          "paper claims require at least one exact source quote before acceptance");
        i.review = decision; i.publication_text = "";
      });
    }
    async publication(key, revision, insight_id, text, confirmed) {
      assert(confirmed === true, "explicit public-export review is required");
      string(text, "publication text", 12000);
      return this.change(key, revision, r => {
        const i = byID(r.insights, insight_id, "insight"); assert(i.review === "accepted", "accept insight first");
        i.publication_text = text;
      });
    }
    async exportPublic(key) {
      const r = await this.read(key); assert(r, "conversation not found");
      return {schema_version: VERSION, kind: "paperflow-public-insights", paper_uids: r.paper_uids,
        insights: r.insights.filter(i => i.review === "accepted" && i.publication_text).map(i => ({insight_id: i.id,
          kind: i.kind, text: i.publication_text}))};
    }
    async exportPrivate(key) {
      const r = await this.read(key); assert(r, "conversation not found");
      return {schema_version: VERSION, kind: "paperflow-private-conversation", conversation: r};
    }
    async importPrivate(bundle) {
      strict(bundle, ["schema_version", "kind", "conversation"], "private bundle");
      assert(bundle.schema_version === VERSION && bundle.kind === "paperflow-private-conversation", "not a private conversation bundle");
      // Validate before changing anything, but never import foreign approvals or
      // pending network jobs. No import can cause an API request or file write
      // outside the fixed journal namespace.
      const source = clone(await validate(bundle.conversation));
      const import_sha256 = await digest(encode(bundle));
      const importID = import_sha256.slice(0, 32);
      const existing = await this.read(importID);
      if (existing) {
        assert(existing.import_sha256 === import_sha256, "import identity collision");
        return existing;
      }
      source.id = importID; source.revision = 1; source.import_sha256 = import_sha256;
      source.updated_at = now(); source.requests = [];
      source.messages.forEach(m => { m.source = "import"; m.status = m.status === "partial" ? "partial" : "imported-unverified"; m.request_id = ""; });
      source.insights.forEach(i => { i.review = "candidate"; i.publication_text = ""; });
      await validate(source);
      try { await this.io.commit(importID, 0, source); } catch (error) {
        const raced = await this.read(importID);
        if (raced?.import_sha256 === import_sha256) return raced;
        throw error;
      }
      return source;
    }
  }
  function markdown(record) {
    const literal = text => String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const block = text => { const n = Math.max(3, ...[...String(text).matchAll(/`+/g)].map(m => m[0].length + 1));
      const f = "`".repeat(n); return `${f}text\n${text}\n${f}`; };
    return [`# PaperFlow research: ${literal(record.title).replace(/\n/g, " ")}`, "",
      `Conversation: ${record.id} · revision ${record.revision}`, "",
      "> Private research export. Quote matching does not establish factual correctness.", "",
      ...record.messages.flatMap(m => [`## ${m.role} · ${m.id}`, `Status: ${m.status}; contexts: ${m.context_ids.join(", ") || "none"}`, "", block(m.content), ""]),
      "## Research insights", "", ...record.insights.flatMap(i => [`### ${i.kind} · ${i.review}`, "", block(i.claim),
        `Sources: ${i.message_ids.join(", ")}`, ...i.evidence.map(e => `Quote matched to ${e.context_id}:\n\n${block(e.quote)}`), ""])].join("\n");
  }
  return Object.freeze({VERSION, LIMITS, ConflictError, Store, assert, id, uid, hash, strict, string,
    parse, encode, clone, digest, token, validate, markdown, endpoint});
});
