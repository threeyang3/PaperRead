"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const scope = { console, URL };
vm.runInNewContext(fs.readFileSync(path.resolve(__dirname, "../../integrations/zotero-paperflow/src/core-client.js"), "utf8"), scope);
const summary = scope.PaperFlowCoreClient.summarizeJobs([
  { kind: "analysis", status: "failed", updated_at: "2026-07-28T13:27:20+08:00" },
  { kind: "render", status: "completed", updated_at: "2026-10-11T17:00:00Z", paper_uid: "arxiv:2504.16054" },
  { kind: "analysis", status: "failed", updated_at: "2026-10-11T16:20:00Z" },
  { kind: "analysis", status: "running", updated_at: "2026-07-28T13:27:20+08:00" },
  { kind: "analysis", status: "failed", updated_at: "invalid" },
  { kind: "analysis", status: "interrupted", updated_at: "2026-10-11 23:55:00" },
], new Date("2026-10-12T02:00:00Z"));
assert.equal(summary.active, 1, "old active jobs must not be hidden as history");
assert.equal(summary.todayFailed, 1, "UTC yesterday can be today in Beijing");
assert.equal(summary.historicalFailed, 2);
assert.equal(summary.undatedFailed, 1);
assert.ok(summary.message.includes("2026-10-12 01:00"));
assert.ok(summary.message.includes("arxiv:2504.16054"));
assert.ok(summary.message.includes("历史失败 2"));
assert.equal(scope.PaperFlowCoreClient.summarizeJobs([]).message, "暂无任务");
console.log("PaperFlow Zotero Beijing-time job status tests passed");
