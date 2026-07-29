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
    if (url.includes("/zotero/pdf/")) {
      const bytes = new TextEncoder().encode("%PDF-1.7\nPaperFlow\n%%EOF\n");
      return {
        ok: true,
        status: 200,
        headers: {
          get(name) {
            if (name === "X-PaperFlow-Sha256") return "a".repeat(64);
            if (name === "X-PaperFlow-Filename") return "arxiv_2504.16054.pdf";
            return "";
          },
        },
        async arrayBuffer() { return bytes.buffer; },
      };
    }
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
  await client.getPaper("arxiv:2504.16054");
  const pdf = await client.paperPdf("arxiv:2504.16054");
  assert.equal(pdf.filename, "arxiv_2504.16054.pdf");
  assert.equal(pdf.sha256, "a".repeat(64));
  assert.equal(new TextDecoder().decode(pdf.bytes).startsWith("%PDF-"), true);
  await client.itemStatus("ABCD1234");
  await client.itemWorkspace("ABCD1234");
  await client.annotations("arxiv:2504.16054");
  await client.importPaper({ paper_uid: "arxiv:2504.16054", paper_title: "π0.5" });
  await client.uploadPdfChunk("arxiv:2504.16054", new Uint8Array([37, 80, 68, 70, 45]), {
    offset: 0, total: 5, sha256: "a".repeat(64), filename: "pi05.pdf", itemKey: "ABCD1234",
  });
  await client.sendEvent({ item_key: "ABCD1234", event: "modify" });
  await client.enqueueAnalysis({ paper_uid: "arxiv:2504.16054" });
  await client.jobs(5);
  await client.job("zotero-analysis-abc");
  await client.migrationResults({ items: [] });
  await client.publishCommunity({ paper_uid: "arxiv:2504.16054", confirm: true });
  await client.communityPaper("arxiv:2504.16054");
  await client.subscriptionInbox({ status: "pending-confirmation", limit: 10 });
  await client.subscriptionInboxItem("arxiv:2504.16054");
  await client.subscriptionStatus();
  await client.subscriptionDecision({ paper_uid: "arxiv:2504.16054", decision: "approve" });
  assert.equal(requests[0].options.headers.Authorization, undefined);
  assert.match(requests[1].url, /papers\/arxiv%3A2504\.16054$/);
  assert.equal(requests[1].options.headers.Authorization, `Bearer ${token}`);
  assert.match(requests[2].url, /zotero\/pdf\/arxiv%3A2504\.16054$/);
  assert.equal(requests[2].options.headers.Authorization, `Bearer ${token}`);
  assert.match(requests[4].url, /zotero\/items\/ABCD1234\/workspace$/);
  assert.match(requests[5].url, /zotero\/annotations/);
  assert.match(requests[6].url, /zotero\/papers\/import$/);
  assert.match(requests[7].url, /zotero\/staging\/arxiv%3A2504\.16054$/);
  assert.equal(requests[7].options.headers["Content-Type"], "application/pdf");
  assert.match(requests[8].url, /zotero\/events$/);
  assert.match(requests[9].url, /analysis\/jobs$/);
  assert.match(requests[10].url, /jobs\?limit=5$/);
  assert.match(requests[11].url, /jobs\/zotero-analysis-abc$/);
  assert.match(requests[12].url, /zotero\/migration\/results$/);
  assert.match(requests[13].url, /community\/publish$/);
  assert.match(requests[14].url, /community\/papers\/arxiv%3A2504\.16054$/);
  assert.match(requests[15].url, /subscriptions\/inbox\?limit=10&status=pending-confirmation$/);
  assert.match(requests[16].url, /subscriptions\/inbox\/arxiv%3A2504\.16054$/);
  assert.match(requests[17].url, /subscriptions\/status$/);
  assert.match(requests[18].url, /subscriptions\/inbox\/decision$/);
  assert.throws(() => new sandbox.PaperFlowCoreClient("https://example.com", token), /loopback/);
  assert.throws(() => client.setToken("short"), /invalid/);
  const noToken = new sandbox.PaperFlowCoreClient();
  await assert.rejects(() => noToken.itemStatus("ABCD1234"), /not configured/);

  const refreshRequests = [];
  let protectedCalls = 0;
  let savedSession = "";
  const refreshSandbox = {
    console,
    URL,
    fetch: async (url, options) => {
      refreshRequests.push({ url, options });
      if (url.endsWith("/zotero/session/refresh")) {
        return {
          ok: true,
          status: 200,
          async json() {
            return { ok: true, session_token: "fedcba9876543210fedcba9876543210" };
          },
        };
      }
      protectedCalls += 1;
      if (protectedCalls === 1) {
        return {
          ok: false,
          status: 401,
          async json() { return { ok: false, error: "authentication required" }; },
        };
      }
      return {
        ok: true,
        status: 200,
        async json() { return { ok: true, jobs: [] }; },
      };
    },
  };
  vm.runInNewContext(source, refreshSandbox, { filename: "core-client-refresh.js" });
  const refreshing = new refreshSandbox.PaperFlowCoreClient(
    "http://127.0.0.1:23140",
    token,
    {
      pairingId: "pairing-1",
      pairingSecret: "pairing-secret-0123456789",
      onSession: (value) => { savedSession = value; },
    }
  );
  const refreshedJobs = await refreshing.jobs(1);
  assert.equal(refreshedJobs.ok, true);
  assert.equal(savedSession, "fedcba9876543210fedcba9876543210");
  assert.equal(refreshRequests.length, 3);
  assert.match(refreshRequests[1].url, /zotero\/session\/refresh$/);
  assert.equal(
    refreshRequests[2].options.headers.Authorization,
    "Bearer fedcba9876543210fedcba9876543210"
  );
  console.log("PaperFlow Zotero Core client tests passed");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
