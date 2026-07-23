"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.resolve(__dirname, "../../integrations/zotero-paperflow/src/core-client.js"),
  "utf8"
);

const requests = [];
const sandbox = {
  console,
  URL,
  fetch: async (url, options) => {
    requests.push({ url, options });
    return {
      ok: true,
      status: 200,
      async json() { return { ok: true, url }; },
    };
  },
};
vm.runInNewContext(source, sandbox, { filename: "core-client.js" });

async function main() {
  const token = "0123456789abcdef0123456789abcdef";
  const client = new sandbox.PaperFlowCoreClient("http://127.0.0.1:23140/", token);
  await client.health();
  await client.itemStatus("ABCD1234");
  await client.sendEvent({ item_key: "ABCD1234", event: "modify" });
  await client.enqueueAnalysis({ paper_uid: "arxiv:2504.16054" });
  assert.equal(requests[0].options.headers.Authorization, undefined);
  assert.equal(requests[1].options.headers.Authorization, `Bearer ${token}`);
  assert.equal(requests[2].options.method, "POST");
  assert.match(requests[3].url, /analysis\/jobs$/);
  assert.throws(() => new sandbox.PaperFlowCoreClient("https://example.com", token), /loopback/);
  assert.throws(() => client.setToken("short"), /invalid/);
  const noToken = new sandbox.PaperFlowCoreClient();
  await assert.rejects(() => noToken.itemStatus("ABCD1234"), /not configured/);
  console.log("PaperFlow Zotero Core client tests passed");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
