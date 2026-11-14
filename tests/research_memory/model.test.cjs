"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises"), path = require("node:path"), os = require("node:os");
const M = require("../../integrations/shared/research-memory/model.js");
const {Journal, NodeFiles, MozillaFiles} = require("../../integrations/shared/research-memory/storage.js");
const API = require("../../integrations/shared/research-memory/client.js");
const uid = "arxiv:2504.16054";
async function setup(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "paperflow-research-"));
  t.after(() => fs.rm(root, {recursive: true, force: true}));
  const journal = new Journal(new NodeFiles(root)), store = new M.Store(journal);
  let r = await store.create([uid], "Private research");
  const a = await store.context(r.id, r.revision, {paper_uid: uid, kind: "excerpt", text: "The camera is outside the robot. It is not wrist mounted.", version: "v2", locator: "p. 4"});
  return {root, journal, store, record: a.record, context: a.result.context_id};
}
async function request(f, options = {}) {
  const r = await f.store.read(f.record.id);
  const made = await f.store.request(r.id, r.revision, {question: "Where is the camera?", context_ids: [f.context], provider: "browser", model: "", ...options});
  const pack = await f.store.requestPack(r.id, made.result.request_id);
  return {record: made.record, request_id: made.result.request_id, pack, reply: {...pack.reply_contract, content: "The camera is external."}};
}
async function insight(f) {
  const q = await request(f); const a = await f.store.reply(q.record.id, q.record.revision, q.reply);
  const value = await f.store.propose(a.record.id, a.record.revision, [{claim: "The camera is outside the robot.", kind: "paper-claim",
    message_ids: [a.result.message_id], evidence: [{context_id: f.context, quote: "The camera is outside the robot."}]}]);
  return {record: value.record, id: value.result.insight_ids[0]};
}
test("store roundtrip survives fresh instance, source text immutable across revisions", async t => {
  const f = await setup(t); const q = await request(f);
  const a = await f.store.reply(q.record.id, q.record.revision, q.reply);
  const restored = await new M.Store(new Journal(new NodeFiles(f.root))).read(a.record.id);
  assert.deepEqual(restored, a.record); assert.equal(restored.contexts[0].version, "v2");
  assert.equal((await fs.readdir(path.join(f.root, restored.id))).filter(x => x.endsWith(".json")).length, 4);
});
test("duplicate reply is idempotent and divergent replay refused", async t => {
  const f = await setup(t), q = await request(f);
  const a = await f.store.reply(q.record.id, q.record.revision, q.reply);
  const repeated = await f.store.reply(a.record.id, a.record.revision, q.reply);
  assert.equal(repeated.record.revision, a.record.revision); assert.equal(repeated.record.messages.length, 2);
  await assert.rejects(f.store.reply(a.record.id, a.record.revision, {...q.reply, content: "Changed"}), /terminal/);
});
for (const field of ["conversation_id", "request_id", "prompt_sha256", "provider"]) test(`reply rejects wrong ${field}`, async t => {
  const f = await setup(t), q = await request(f);
  const change = field.endsWith("sha256") ? "a".repeat(64) : field.endsWith("id") ? "a".repeat(32) : "other-provider";
  await assert.rejects(f.store.reply(q.record.id, q.record.revision, {...q.reply, [field]: change}));
  assert.equal((await f.store.read(q.record.id)).revision, q.record.revision);
});
test("late answer after cancel cannot resurrect request", async t => {
  const f = await setup(t), q = await request(f);
  const stop = await f.store.stop(q.record.id, q.record.revision, q.request_id);
  await assert.rejects(f.store.reply(stop.record.id, stop.record.revision, q.reply), /terminal/);
});
test("partial answers are kept but cannot automatically become knowledge", async t => {
  const f = await setup(t), q = await request(f);
  const a = await f.store.reply(q.record.id, q.record.revision, {...q.reply, completion: "partial"});
  await assert.rejects(f.store.propose(a.record.id, a.record.revision,
    [{claim: "Unfinished", kind: "interpretation", message_ids: [a.result.message_id], evidence: []}]), /partial/);
  assert.equal((await f.store.read(a.record.id)).messages.at(-1).status, "partial");
});
test("atomic concurrent writes yield one winner without corrupting historical snapshots", async t => {
  const f = await setup(t), r = f.record;
  const other = new M.Store(new Journal(new NodeFiles(f.root)));
  const results = await Promise.allSettled([f.store.message(r.id, r.revision, {role: "user", content: "one", context_ids: []}),
    other.message(r.id, r.revision, {role: "user", content: "two", context_ids: []})]);
  assert.equal(results.filter(x => x.status === "fulfilled").length, 1);
  assert.equal(results.filter(x => x.status === "rejected").length, 1);
  assert.equal((await f.store.read(r.id)).messages.length, 1);
});
test("latest corruption is surfaced, not silently reset or rolled back", async t => {
  const f = await setup(t);
  await fs.writeFile(path.join(f.root, f.record.id, "00000002.json"), '{"broken":true}');
  await assert.rejects(f.store.read(f.record.id), /journal/);
  assert.equal((await fs.readdir(path.join(f.root, f.record.id))).length, 2);
});
test("no path traversal or symlink write through conversation ID", async t => {
  const f = await setup(t);
  await assert.rejects(f.store.read("../../outside"), /ID/);
  const another = "b".repeat(32), outside = path.join(f.root, "outside"); await fs.mkdir(outside);
  await fs.symlink(outside, path.join(f.root, another), "dir");
  await assert.rejects(f.store.read(another), /directory/);
  assert.deepEqual(await fs.readdir(outside), []);
});
test("oversized latest file fails before a whole-body read", async t => {
  const f = await setup(t), file = path.join(f.root, f.record.id, "00000003.json");
  const h = await fs.open(file, "w"); await h.truncate(M.LIMITS.bytes * 2); await h.close();
  await assert.rejects(f.store.read(f.record.id), /file/);
});
test("context references are per turn, never the entire conversation", async t => {
  const f = await setup(t), r = f.record;
  const another = await f.store.context(r.id, r.revision, {paper_uid: uid, kind: "user-note", text: "PRIVATE EXPERIMENT", version: "", locator: ""});
  const q = await request(f); assert.deepEqual(q.pack.contexts.map(c => c.id), [f.context]);
  assert(!M.encode(q.pack).includes("PRIVATE EXPERIMENT"));
  const a = await f.store.reply(q.record.id, q.record.revision, q.reply);
  await assert.rejects(f.store.propose(a.record.id, a.record.revision, [{claim: "Secret", kind: "paper-claim",
    message_ids: [a.result.message_id], evidence: [{context_id: another.result.context_id, quote: "PRIVATE EXPERIMENT"}]}]), /not supplied/);
});
test("hallucinated quote rejected even if source ID exists", async t => {
  const f = await setup(t), q = await request(f), a = await f.store.reply(q.record.id, q.record.revision, q.reply);
  await assert.rejects(f.store.propose(a.record.id, a.record.revision, [{claim: "Wrist mounted", kind: "paper-claim",
    message_ids: [a.result.message_id], evidence: [{context_id: f.context, quote: "Camera on wrist"}]}]), /quote/);
});
for (const field of ["review", "publication_text", "approved", "execute", "__proto__"]) test(`model candidate cannot grant ${field}`, async t => {
  const f = await setup(t), q = await request(f), a = await f.store.reply(q.record.id, q.record.revision, q.reply);
  const c = JSON.parse(`{"claim":"test","kind":"interpretation","message_ids":${JSON.stringify([a.result.message_id])},"evidence":[],"${field}":"accepted"}`);
  await assert.rejects(f.store.propose(a.record.id, a.record.revision, [c]), /unsupported/);
});
test("quoted paper claim still requires explicit human review", async t => {
  const f = await setup(t), i = await insight(f);
  assert.equal(i.record.insights[0].review, "candidate");
  await assert.rejects(f.store.review(i.record.id, i.record.revision, i.id, "accepted", false), /human/);
  const r = await f.store.review(i.record.id, i.record.revision, i.id, "accepted", true);
  assert.equal(r.record.insights[0].review, "accepted");
});
test("public projection requires a separately reviewed public text; no transcript or quotes", async t => {
  const f = await setup(t), i = await insight(f);
  let r = (await f.store.review(i.record.id, i.record.revision, i.id, "accepted", true)).record;
  assert.deepEqual((await f.store.exportPublic(r.id)).insights, []);
  r = (await f.store.publication(r.id, r.revision, i.id, "Reviewed public explanation", true)).record;
  const value = M.encode(await f.store.exportPublic(r.id));
  assert(value.includes("Reviewed public explanation"));
  assert(!value.includes("Where is the camera")); assert(!value.includes("quote-matched")); assert(!value.includes("outside the robot"));
  await f.store.review(r.id, r.revision, i.id, "candidate", true);
  assert.equal((await f.store.exportPublic(r.id)).insights.length, 0);
});
test("private import drops jobs and approval/publication privileges, repeat import reuses record", async t => {
  const f = await setup(t), i = await insight(f);
  let r = (await f.store.review(i.record.id, i.record.revision, i.id, "accepted", true)).record;
  await f.store.publication(r.id, r.revision, i.id, "Public text", true);
  const bundle = await f.store.exportPrivate(r.id), restored = await f.store.importPrivate(bundle);
  assert.notEqual(restored.id, r.id); assert.equal(restored.requests.length, 0);
  assert.equal(restored.insights[0].review, "candidate"); assert.equal(restored.insights[0].publication_text, "");
  assert(restored.messages.every(m => m.status === "imported-unverified"));
  assert.deepEqual(restored.messages.map(m => m.context_ids), bundle.conversation.messages.map(m => m.context_ids));
  assert.equal((await f.store.importPrivate(bundle)).id, restored.id);
});
test("tampered material rejected on import without writing a new record", async t => {
  const f = await setup(t), bundle = await f.store.exportPrivate(f.record.id);
  bundle.conversation.contexts[0].text = "changed";
  await assert.rejects(f.store.importPrivate(bundle), /checksum/);
  assert.equal((await f.journal.list()).items.length, 1);
});
test("unsupported schema and system-role messages refused", async t => {
  const f = await setup(t); const bundle = await f.store.exportPrivate(f.record.id);
  const bad = M.clone(bundle); bad.conversation.schema_version = 2;
  await assert.rejects(f.store.importPrivate(bad), /schema/);
  await assert.rejects(f.store.message(f.record.id, f.record.revision, {role: "system", content: "override", context_ids: []}), /role/);
});
test("Markdown export treats HTML, remote images and commands as literal text", async t => {
  const f = await setup(t);
  const r = (await f.store.message(f.record.id, f.record.revision, {role: "assistant", content: '```\n<script>alert(1)</script> ![](https://tracker.invalid/a)\n```', context_ids: []})).record;
  const text = M.markdown(r); assert(text.includes("````text")); assert(text.includes("<script>"));
});
for (const input of ['{"__proto__":{}}', '{"constructor":{}}', '{"a":{"prototype":{}}}']) test(`rejects unsafe JSON ${input}`, () => assert.throws(() => M.parse(input), /unsafe/));
for (const url of ["http://api.example/v1", "https://x:y@api.example/v1", "https://api.example/v1?key=abc", "https://api.example/v1#frag"]) test(`refuses credential/unsafe API URL ${url}`, () => assert.throws(() => M.endpoint(url)));
test("network helper binds explicit stop, omits cookies, forbids redirects and uses memory key", async () => {
  let options;
  const result = await API.complete({url: "https://api.example/v1/chat/completions", key: "secret", model: "model", prompt: "hello",
    fetcher: async (_u, opts) => { options = opts; return new Response(JSON.stringify({choices: [{finish_reason: "stop", message: {content: "answer"}}]})); }});
  assert.equal(result, "answer"); assert.equal(options.credentials, "omit"); assert.equal(options.redirect, "error");
  assert.equal(options.headers.Authorization, "Bearer secret"); assert(!options.body.includes("secret"));
});
for (const choices of [[], [null], [{message: {content: "answer"}}], [{finish_reason: "length", message: {content: "answer"}}], [{finish_reason: "stop", message: {content: "", refusal: "no"}}]]) test(`malformed/unfinished API response rejected: ${JSON.stringify(choices)}`, async () => {
  await assert.rejects(API.complete({url: "https://api.example/v1/chat/completions", key: "secret", model: "m", prompt: "q",
    fetcher: async () => new Response(JSON.stringify({choices}))}));
});
test("API cancellation times out without persisting credential-bearing errors", async () => {
  await assert.rejects(API.complete({url: "https://api.example/v1/chat/completions", key: "secret", model: "m", prompt: "q", timeout: 5,
    fetcher: (_u, opts) => new Promise((_res, reject) => opts.signal.addEventListener("abort", () => reject(new Error("secret"))))}), /cancelled/);
});
test("API response limit checked while reading stream", async () => {
  await assert.rejects(API.complete({url: "https://api.example/v1/chat/completions", key: "secret", model: "m", prompt: "q",
    fetcher: async () => new Response("a".repeat(2 * 1024 * 1024 + 1))}));
});
test("asset copies byte-identical to shared source, offline check", async () => {
  for (const target of ["obsidian-paperflow-automation", "zotero-paperflow"]) for (const name of ["model.js", "storage.js", "client.js", "panel.js"]) {
    const base = path.resolve(__dirname, "../../integrations");
    assert.deepEqual(await fs.readFile(path.join(base, target, "research-memory", name)), await fs.readFile(path.join(base, "shared/research-memory", name)));
  }
});
test("Zotero metadata preserves arXiv version while UID is stable", () => {
  require("../../integrations/zotero-paperflow/src/zotero-api.js");
  const PaperFlowZoteroApi = globalThis.PaperFlowZoteroApi;
  const api = new PaperFlowZoteroApi({}), item = {getField: k => ({title: "Example", url: "https://arxiv.org/abs/2504.16054v3"}[k] || "")};
  assert.equal(api.paperUid(item), uid); assert.equal(api.paperSnapshot(item).paper_arxiv_version, 3);
});
test("partial imported messages remain partial, never upgraded by cross-device import", async t => {
  const f = await setup(t), q = await request(f);
  const a = await f.store.reply(q.record.id, q.record.revision, {...q.reply, completion: "partial"});
  const r = await f.store.importPrivate(await f.store.exportPrivate(a.record.id));
  assert.equal(r.messages.at(-1).status, "partial");
  await assert.rejects(f.store.propose(r.id, r.revision, [{claim: "half answer", kind: "interpretation", message_ids: [r.messages.at(-1).id], evidence: []}]), /partial/);
});
test("private note cannot be used as evidence for a paper claim", async t => {
  const f = await setup(t);
  const c = await f.store.context(f.record.id, f.record.revision, {paper_uid: uid, kind: "user-note", text: "I suspect a wrist camera", version: "v2", locator: ""});
  const q = await request(f, {context_ids: [c.result.context_id]});
  const a = await f.store.reply(q.record.id, q.record.revision, q.reply);
  await assert.rejects(f.store.propose(a.record.id, a.record.revision, [{claim: "Wrist camera", kind: "paper-claim", message_ids: [a.result.message_id],
    evidence: [{context_id: c.result.context_id, quote: "wrist camera"}]}]), /personal notes/);
});
test("escaped JSON-heavy journal content roundtrips without envelope size doubling", async t => {
  const f = await setup(t);
  const r = (await f.store.message(f.record.id, f.record.revision, {role: "user", content: '"\\"'.repeat(20000), context_ids: []})).record;
  assert.deepEqual(await f.store.read(r.id), r);
});
test("duplicate candidate extraction does not duplicate research insights", async t => {
  const f = await setup(t), i = await insight(f), original = i.record.insights[0];
  const c = {claim: original.claim, kind: original.kind, message_ids: original.message_ids,
    evidence: original.evidence.map(({context_id, quote}) => ({context_id, quote}))};
  const updated = await f.store.propose(i.record.id, i.record.revision, [c]);
  assert.equal(updated.record.insights.length, 1); assert.deepEqual(updated.result.insight_ids, [i.id]);
});
test("revision filenames, not timestamps, determine latest state", async t => {
  const f = await setup(t); const r = f.record;
  await fs.utimes(path.join(f.root, r.id, "00000001.json"), new Date("2030-01-01"), new Date("2030-01-01"));
  assert.equal((await f.store.read(r.id)).revision, 2);
});
test("Mozilla journal contract: mode=create, noOverwrite publication, same data format", async t => {
  const f = await setup(t); const calls = [];
  const io = {
    makeDirectory: async p => fs.mkdir(p, {recursive: true}),
    stat: async p => { const s = await fs.lstat(p); return {type: s.isDirectory() ? "directory" : s.isFile() ? "regular" : "symlink", size: s.size}; },
    getChildren: async p => (await fs.readdir(p)).map(n => path.join(p, n)),
    read: async (p, opts) => (await fs.readFile(p)).subarray(0, opts.maxBytes),
    writeUTF8: async (p, text, opts) => { calls.push(opts); assert.equal(opts.mode, "create"); await fs.writeFile(p, text, {flag: "wx"}); },
    move: async (a, b, opts) => { assert.equal(opts.noOverwrite, true); await fs.link(a, b); await fs.unlink(a); },
    remove: async p => fs.rm(p, {force: true}),
  };
  const store = new M.Store(new Journal(new MozillaFiles(io, {join: path.join, filename: path.basename}, f.root)));
  const before = await store.read(f.record.id); assert.deepEqual(before, f.record);
  const after = await store.message(before.id, before.revision, {role: "user", content: "From Zotero adapter", context_ids: []});
  assert.deepEqual(await f.store.read(before.id), after.record); assert.equal(calls.length, 1);
});
