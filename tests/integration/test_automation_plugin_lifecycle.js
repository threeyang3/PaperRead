"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const Module = require("node:module");
const os = require("node:os");
const path = require("node:path");

const fixtureVaultRoot = fs.mkdtempSync(
  path.join(os.tmpdir(), "paperflow-automation-vault-")
);
fs.mkdirSync(path.join(fixtureVaultRoot, ".paperflow"), { recursive: true });
fs.writeFileSync(
  path.join(fixtureVaultRoot, ".paperflow", "workspace.yaml"),
  "workspace_name: Lifecycle Test\ntimezone: Asia/Shanghai\n",
  "utf8"
);

let layoutReady;
const vaultEvents = [];
const registeredEvents = [];
const registeredIntervals = [];
const registeredViews = [];
const ribbonIcons = [];
const registeredCommands = [];
const saved = [];
const openedLinks = [];
let revealedLeaf = null;
let openedModal = null;

class FakeElement {
  constructor(tag = "div", options = {}) {
    this.tag = tag;
    this.children = [];
    this.classes = new Set();
    this.listeners = {};
    this.text = options.text || "";
    if (options.cls) {
      for (const name of String(options.cls).split(/\s+/).filter(Boolean)) {
        this.classes.add(name);
      }
    }
  }

  createDiv(options = {}) {
    return this.createEl("div", options);
  }

  createEl(tag, options = {}) {
    const child = new FakeElement(tag, options);
    this.children.push(child);
    return child;
  }

  createSpan(options = {}) {
    return this.createEl("span", options);
  }

  addClass(name) {
    this.classes.add(name);
  }

  addEventListener(name, callback) {
    this.listeners[name] = callback;
  }

  empty() {
    this.children = [];
  }

  setText(value) {
    this.text = String(value);
  }

  toggleClass(name, enabled) {
    if (enabled) this.classes.add(name);
    else this.classes.delete(name);
  }

  findByClass(name) {
    const result = this.classes.has(name) ? [this] : [];
    return result.concat(...this.children.map((child) => child.findByClass(name)));
  }
}

class Plugin {
  constructor() {
    this.app = {
      workspace: {
        onLayoutReady(callback) {
          layoutReady = callback;
        },
        getLeavesOfType() {
          return [];
        },
        getRightLeaf() {
          return {
            async setViewState(state) {
              this.state = state;
            }
          };
        },
        revealLeaf(leaf) {
          revealedLeaf = leaf;
        },
        async openLinkText(target, source, newLeaf) {
          openedLinks.push({ target, source, newLeaf });
        },
        on(name, callback) {
          return { name, callback };
        }
      },
      metadataCache: {
        getFileCache() {
          return { frontmatter: null };
        }
      },
      vault: {
        adapter: {
          getBasePath() {
            return fixtureVaultRoot;
          }
        },
        on(name, callback) {
          vaultEvents.push({ name, callback });
          return { name };
        },
        getMarkdownFiles() {
          return [];
        }
      },
      commands: {
        commands: {},
        executeCommandById() {
          return false;
        }
      }
    };
  }

  async loadData() {
    return {
      enabled: true,
      dailyLocalTime: "08:00",
      inboxIntervalMinutes: 5,
      runtime: { lastDailyDate: "2026-07-17" }
    };
  }

  async saveData(value) {
    saved.push(value);
  }

  addStatusBarItem() {
    return {
      setText() {},
      setAttr() {}
    };
  }

  addCommand(command) {
    registeredCommands.push(command);
  }
  addSettingTab() {}
  addRibbonIcon(icon, title) {
    ribbonIcons.push({ icon, title });
  }
  registerView(type, factory) {
    registeredViews.push({ type, factory });
  }
  register(disposer) {
    this.disposer = disposer;
  }
  registerEvent(event) {
    registeredEvents.push(event);
  }
  registerInterval(interval) {
    registeredIntervals.push(interval);
  }
}

class PluginSettingTab {}
class Setting {}
class Notice {}
class ItemView {
  constructor(leaf) {
    this.leaf = leaf;
    this.app = leaf.app;
    this.contentEl = new FakeElement();
    this.containerEl = this.contentEl;
  }
}
class Modal {
  constructor(app) {
    this.app = app;
    this.contentEl = new FakeElement();
  }
  open() {
    openedModal = this;
    this.onOpen?.();
  }
  close() {
    this.onClose?.();
  }
}

const originalLoad = Module._load;
const relativeModuleRequests = [];
Module._load = function load(request, parent, isMain) {
  if (request === "obsidian") {
    return {
      Plugin,
      PluginSettingTab,
      Setting,
      Notice,
      ItemView,
      Modal,
      setIcon() {},
      Platform: { isDesktopApp: true }
    };
  }
  if (/^\.\.?[\\/]/.test(request)) {
    relativeModuleRequests.push(request);
    const error = new Error(`Cannot find module '${request}'`);
    error.code = "MODULE_NOT_FOUND";
    throw error;
  }
  return originalLoad.call(this, request, parent, isMain);
};

let nextTimer = 1;
global.window = {
  setInterval() {
    return nextTimer++;
  },
  setTimeout() {
    return nextTimer++;
  },
  clearTimeout() {}
};

async function main() {
  const pluginMain = path.resolve(
    __dirname,
    "../../integrations/obsidian-paperflow-automation/main.js"
  );
  const originalCwd = process.cwd();
  let AutomationPlugin;
  try {
    process.chdir(os.tmpdir());
    AutomationPlugin = require(pluginMain);
  } finally {
    process.chdir(originalCwd);
  }
  assert.deepEqual(relativeModuleRequests, []);
  const redact = AutomationPlugin.__test.redactAutomationLog;
  const redactionCases = [
    ["token=secret", "secret"],
    ["token: secret", "secret"],
    ['{"token": "json-secret-suffix"}', "json-secret-suffix"],
    ["{'password': 'single-quoted-secret'}", "single-quoted-secret"],
    ["Authorization: Bearer bearer-secret-suffix", "bearer-secret-suffix"],
    ["authorization=Bearer lower-secret-suffix", "lower-secret-suffix"],
    ["Cookie: session=cookie-secret-suffix", "cookie-secret-suffix"],
    ["Set-Cookie: session=set-cookie-secret-suffix", "set-cookie-secret-suffix"],
    ["OPENAI_API_KEY=env-openai-secret", "env-openai-secret"],
    ["ANTHROPIC_API_KEY=env-anthropic-secret", "env-anthropic-secret"],
    ["GITHUB_TOKEN=env-github-secret", "env-github-secret"],
    ['PaSsWoRd: "mixed-case-secret"', "mixed-case-secret"]
  ];
  for (const [input, secret] of redactionCases) {
    const output = redact(input);
    assert.ok(!output.includes(secret), `${input} leaked through as ${output}`);
    assert.match(output, /\[REDACTED\]/);
  }
  assert.equal(typeof AutomationPlugin.__test.openReadingWorkspace, "function");
  assert.equal(
    AutomationPlugin.__test.workspaceTimezoneFromYaml(
      "workspace_name: Test\ntimezone: \"Asia/Tokyo\"\nlanguage: auto\n"
    ),
    "Asia/Tokyo"
  );
  assert.throws(
    () => AutomationPlugin.__test.workspaceTimezoneFromYaml(
      "workspace_name: Test\ntimezone: Mars/Olympus\n"
    ),
    /Invalid Workspace timezone/
  );

  const paper = { path: "10 Papers/2025/pi05.md", extension: "md" };
  const pdf = { path: "80 Attachments/Papers/2025/2504.16054/v1.pdf", extension: "pdf" };
  const annotation = { path: "Private Notes/Annotations/arxiv_2504.16054/index.md" };
  const review = { path: "60 Reviews/2025/arxiv_2504.16054.review.md" };
  const community = { path: "70 Community/2025/arxiv_2504.16054.community.md" };
  const files = new Map([
    [pdf.path, pdf],
    [annotation.path, annotation],
    [review.path, review],
    [community.path, community]
  ]);
  const layoutLeaves = [];
  const makeLeaf = (name) => {
    const leaf = {
      name,
      async openFile(file) {
        this.file = file;
      }
    };
    layoutLeaves.push(leaf);
    return leaf;
  };
  const pdfLeaf = makeLeaf("pdf");
  const annotationLeaf = makeLeaf("annotation");
  const reviewLeaf = makeLeaf("review");
  const communityLeaf = makeLeaf("community");
  const layoutWorkspace = {
    getActiveFile() {
      return paper;
    },
    getLeaf(kind, direction) {
      assert.equal(kind, "split");
      assert.equal(direction, "vertical");
      return pdfLeaf;
    },
    createLeafBySplit(anchor, direction) {
      assert.equal(anchor, pdfLeaf);
      assert.equal(direction, "horizontal");
      return reviewLeaf;
    },
    getRightLeaf(split) {
      return split ? communityLeaf : annotationLeaf;
    },
    async revealLeaf(leaf) {
      await Promise.resolve();
      this.revealedLeaf = leaf;
    },
    setActiveLeaf(leaf, options) {
      this.activeLeaf = leaf;
      this.activeOptions = options;
    }
  };
  const layoutApp = {
    workspace: layoutWorkspace,
    metadataCache: {
      getFileCache() {
        return {
          frontmatter: {
            type: "paper",
            paper_uid: "arxiv:2504.16054",
            paper_year: 2025,
            paper_pdf_path: pdf.path
          }
        };
      }
    },
    vault: {
      getAbstractFileByPath(filePath) {
        return files.get(filePath);
      }
    }
  };
  const workspacePlugin = new AutomationPlugin();
  workspacePlugin.app = layoutApp;
  let indexRequest = null;
  workspacePlugin.runControlAction = async (action, payload) => {
    indexRequest = { action, payload };
    return { code: 0, stdout: JSON.stringify({ path: annotation.path }), stderr: "" };
  };
  const layoutResult = await workspacePlugin.openPaperReadingWorkspace();
  assert.deepEqual(indexRequest, {
    action: "annotation-index",
    payload: { paperUid: "arxiv:2504.16054" }
  });
  assert.equal(new Set(layoutLeaves).size, 4);
  assert.equal(pdfLeaf.file, pdf);
  assert.equal(annotationLeaf.file, annotation);
  assert.equal(reviewLeaf.file, review);
  assert.equal(communityLeaf.file, community);
  assert.equal(layoutWorkspace.revealedLeaf, pdfLeaf);
  assert.equal(layoutWorkspace.activeLeaf, pdfLeaf);
  assert.deepEqual(layoutWorkspace.activeOptions, { focus: true });
  assert.deepEqual(layoutResult, {
    paper: paper.path,
    pdf: pdf.path,
    annotation: annotation.path,
    review: review.path,
    community: community.path
  });
  assert.deepEqual(AutomationPlugin.__test.activePaperContext({
    workspace: { getActiveFile: () => pdf },
    vault: { getMarkdownFiles: () => [paper] },
    metadataCache: {
      getFileCache: () => ({
        frontmatter: {
          type: "paper",
          paper_uid: "arxiv:2504.16054",
          paper_pdf_path: pdf.path,
          paper_arxiv_version: "v1"
        }
      })
    }
  }), {
    paperUid: "arxiv:2504.16054",
    pdfPath: pdf.path,
    pdfVersion: 1
  });
  assert.deepEqual(
    AutomationPlugin.__test.controlCommands("paper-add", {
      value: "2607.00001",
      priority: 5,
      ai: false
    }),
    [[
      "paper", "add", "2607.00001", "--priority", "5", "--no-ai"
    ]]
  );
  assert.deepEqual(
    AutomationPlugin.__test.controlCommands("paper-analyze", {
      paperUid: "arxiv:2607.15275",
      provider: "configured"
    }),
    [["paper", "analyze", "arxiv:2607.15275"]]
  );
  assert.deepEqual(
    AutomationPlugin.__test.controlCommands("paper-analyze", {
      paperUid: "arxiv:2607.15275",
      provider: "codex"
    }),
    [["paper", "analyze", "arxiv:2607.15275", "--provider", "codex"]]
  );
  assert.deepEqual(
    AutomationPlugin.__test.controlCommands("paper-visuals"),
    [["paper", "visuals", "--all"]]
  );
  const selectionLink = "[[80 Attachments/Papers/2026/2607.00001/v3.pdf#page=9&selection=4,1,7,22&color=yellow]]";
  assert.deepEqual(
    AutomationPlugin.__test.parsePdfAnnotationLink(selectionLink),
    {
      raw: selectionLink,
      path: "80 Attachments/Papers/2026/2607.00001/v3.pdf",
      page: 9,
      selection: "4,1,7,22",
      color: "yellow"
    }
  );
  assert.deepEqual(
    AutomationPlugin.__test.parsePdfAnnotationLink(
      "[[80 Attachments/Papers/2026/2607.00001/v3.pdf#page=9&amp;selection=4,1,7,22&amp;color=yellow]]"
    ),
    {
      raw: selectionLink,
      path: "80 Attachments/Papers/2026/2607.00001/v3.pdf",
      page: 9,
      selection: "4,1,7,22",
      color: "yellow"
    }
  );
  const annotationPayloadValue = AutomationPlugin.__test.annotationPayload({
    paperUid: "arxiv:2607.00001",
    pdfPath: "80 Attachments/Papers/2026/2607.00001/v3.pdf",
    pdfVersion: 3
  }, {
    pdfLink: selectionLink,
    kind: "question",
    selectedText: "Why is this stable?",
    body: "Check the proof."
  });
  assert.deepEqual(
    AutomationPlugin.__test.controlCommands("annotation-create", annotationPayloadValue),
    [[
      "annotation", "create", "arxiv:2607.00001", selectionLink,
      "--kind", "question", "--motivation", "questioning",
      "--body", "Check the proof.",
      "--selected-text", "Why is this stable?",
      "--pdf-version", "3", "--apply"
    ]]
  );
  assert.deepEqual(
    AutomationPlugin.__test.controlCommands("annotation-index", {
      paperUid: "arxiv:2607.00001"
    }),
    [["annotation", "ensure-index", "arxiv:2607.00001", "--apply"]]
  );
  assert.throws(
    () => AutomationPlugin.__test.parsePdfAnnotationLink(
      "[[80 Attachments/paper.pdf#page=1&selection=fabricated%20text]]"
    ),
    /四个整数/
  );
  let executedCommand = "";
  const adapter = await AutomationPlugin.__test.copyPdfPlusSelectionLink({
    commands: {
      commands: { [AutomationPlugin.__test.PDF_PLUS_SELECTION_COMMAND]: {} },
      executeCommandById(command) {
        executedCommand = command;
        return true;
      }
    }
  }, "80 Attachments/Papers/2026/2607.00001/v3.pdf", {
    async readText() {
      return selectionLink;
    }
  });
  assert.equal(adapter.ok, true);
  assert.equal(adapter.link, selectionLink);
  assert.equal(executedCommand, "pdf-plus:copy-link-to-selection");
  assert.deepEqual(
    await AutomationPlugin.__test.copyPdfPlusSelectionLink(
      { commands: { commands: {}, executeCommandById() {} } },
      "80 Attachments/Papers/2026/2607.00001/v3.pdf",
      { async readText() { return selectionLink; } }
    ),
    { ok: false, reason: "command-unavailable" }
  );
  assert.deepEqual(
    AutomationPlugin.__test.controlCommands("rebuild-relationships"),
    [["rebuild-relationships"]]
  );
  assert.deepEqual(
    AutomationPlugin.__test.controlCommands("source-add", {
      url: "https://github.com/example/feed",
      name: "robotics-feed"
    }),
    [[
      "source",
      "add",
      "https://github.com/example/feed.git",
      "--name",
      "robotics-feed"
    ]]
  );
  assert.deepEqual(
    AutomationPlugin.__test.controlCommands("source-trust", {
      name: "robotics-feed",
      mode: "metadata-only"
    }),
    [["source", "trust", "robotics-feed", "metadata-only"]]
  );
  assert.deepEqual(
    AutomationPlugin.__test.controlCommands("publish-auto"),
    [["publish", "auto", "--push", "--confirm-automation"]]
  );
  assert.deepEqual(
    AutomationPlugin.__test.controlCommands("update-save", {
      repository: "https://github.com/example/PaperFlow",
      autoCheck: true,
      autoStage: true
    }),
    [[
      "update", "configure",
      "--repository-url", "https://github.com/example/PaperFlow.git",
      "--auto-check", "--auto-stage"
    ]]
  );
  assert.deepEqual(
    AutomationPlugin.__test.controlCommands("ai-save", {
      profile: "full_analysis",
      provider: "codex",
      model: "gpt-5.4",
      timeout: 1200,
      reasoningEffort: "high",
      fallback: true,
      reuseFeed: true,
      reanalyzeWhen: "identity-changed"
    }),
    [[
      "ai",
      "set-profile",
      "full_analysis",
      "--provider",
      "codex",
      "--model",
      "gpt-5.4",
      "--timeout",
      "1200",
      "--reasoning-effort",
      "high",
      "--fallback",
      "--reuse-feed",
      "--reanalyze-when",
      "identity-changed"
    ]]
  );
  assert.deepEqual(
    AutomationPlugin.__test.controlCommands("publish-configure", {
      feedId: "robotics-feed",
      name: "Robotics Feed",
      publisherName: "Example",
      publisherUrl: "https://example.org",
      dataLicense: "USER-SELECTED",
      remote: "https://github.com/example/robotics-feed",
      branch: "main"
    })[0].slice(0, 6),
    [
      "publish",
      "configure",
      "--feed-id",
      "robotics-feed",
      "--name",
      "Robotics Feed"
    ]
  );
  assert.throws(
    () => AutomationPlugin.__test.controlCommands("shell", { command: "whoami" }),
    /不允许/
  );
  assert.throws(
    () => AutomationPlugin.__test.githubUrl("https://example.com/feed"),
    /github/
  );
  global.localStorage = { getItem: () => "zh-CN" };
  assert.equal(AutomationPlugin.__test.isChinese(), true);
  assert.equal(AutomationPlugin.__test.text("中文", "English"), "中文");
  assert.equal(
    Object.keys(AutomationPlugin.__test.PAPER_PROPERTY_LABELS_ZH).length,
    85
  );
  const propertyCss = AutomationPlugin.__test.propertyLabelCss();
  assert.match(propertyCss, /data-property-key="paper_title"/);
  assert.match(propertyCss, /content:"论文标题"/);
  assert.match(propertyCss, /metadata-property-key-input:focus/);
  global.localStorage = { getItem: () => "en" };
  assert.equal(AutomationPlugin.__test.isChinese(), false);
  assert.equal(AutomationPlugin.__test.text("中文", "English"), "English");
  const plugin = new AutomationPlugin();
  plugin.writeLocaleMarker = async () => {};
  plugin.checkDaily = async () => {};
  plugin.runJob = async () => {};

  await plugin.onload();
  assert.equal(plugin.activeChild, null);
  assert.equal(plugin.activeJob, null);
  assert.equal(plugin.activeJobStartedAt, "");
  assert.equal(plugin.activeJobAbortReason, "");
  assert.equal(typeof plugin.cancelActiveJob, "function");
  assert.deepEqual(
    AutomationPlugin.__test.windowsProcessTreeCommand(4321),
    {
      command: "taskkill",
      args: ["/PID", "4321", "/T", "/F"]
    }
  );
  const currentPaper = { path: "10 Papers/2607.00001.md", extension: "md" };
  plugin.app.workspace.getActiveFile = () => currentPaper;
  plugin.app.metadataCache.getFileCache = () => ({
    frontmatter: {
      type: "paper",
      paper_uid: "arxiv:2607.00001",
      paper_pdf_path: "80 Attachments/Papers/2026/2607.00001/v3.pdf",
      paper_arxiv_version: 3
    }
  });
  const annotationCommand = registeredCommands.find((item) => item.id === "create-pdf-annotation");
  assert.ok(annotationCommand);
  annotationCommand.callback();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.ok(openedModal);
  assert.equal(openedModal.contentEl.findByClass("paperflow-annotation-modal").length, 1);
  assert.equal(openedModal.contentEl.findByClass("paperflow-annotation-field").length, 5);
  assert.equal(typeof layoutReady, "function");
  layoutReady();
  await new Promise((resolve) => setTimeout(resolve, 75));

  assert.deepEqual(
    vaultEvents.map((event) => event.name),
    ["create", "modify", "rename"]
  );
  assert.equal(registeredEvents.length, 4);
  assert.equal(registeredIntervals.length, 2);
  assert.equal(registeredViews.length, 1);
  assert.equal(registeredViews[0].type, "paperflow-control-center");
  assert.equal(ribbonIcons.length, 2);
  const view = registeredViews[0].factory({ app: plugin.app });
  await view.onOpen();
  assert.equal(view.contentEl.findByClass("paperflow-control-hero").length, 1);
  assert.equal(view.contentEl.findByClass("paperflow-automation-grid").length, 1);
  assert.equal(view.contentEl.findByClass("paperflow-automation-track").length, 3);
  assert.equal(view.contentEl.findByClass("paperflow-task-shelf").length, 1);
  assert.equal(view.contentEl.findByClass("paperflow-task-entry").length, 7);
  await view.contentEl
    .findByClass("paperflow-task-entry")[0]
    .findByClass("paperflow-action")[0]
    .listeners.click();
  assert.deepEqual(openedLinks, [
    {
      target: "90 System/Forms/Add Paper",
      source: "",
      newLeaf: true
    }
  ]);
  assert.equal(view.contentEl.findByClass("paperflow-primary-grid").length, 1);
  assert.equal(view.contentEl.findByClass("paperflow-agent-boundary").length, 1);
  assert.equal(view.contentEl.findByClass("paperflow-advanced-tools").length, 1);
  assert.ok(view.contentEl.findByClass("paperflow-action").length >= 25);
  assert.equal(view.contentEl.findByClass("paperflow-output").length, 1);
  assert.equal(saved.length, 0);
  assert.equal(revealedLeaf.state.type, "paperflow-control-center");
  assert.equal(revealedLeaf.state.active, true);
  assert.equal(plugin.started, true);
  assert.equal(AutomationPlugin.__test.intervalDue("", 60), true);

  const childRoot = fs.mkdtempSync(
    path.join(os.tmpdir(), "paperflow-automation-child-")
  );
  plugin.runningJob = "timeout-test";
  const timeoutStarted = Date.now();
  const timedOut = await plugin.spawnPaperFlow(
    process.execPath,
    "",
    childRoot,
    ["-e", "setTimeout(() => {}, 60000)"],
    { action: "timeout-test", timeoutSeconds: 0.1, gracefulMs: 50 }
  );
  assert.equal(timedOut.code, 124);
  assert.equal(timedOut.timedOut, true);
  assert.ok(Date.now() - timeoutStarted < 5000);
  assert.equal(plugin.activeChild, null);
  assert.equal(plugin.settings.runtime.activeJob, null);

  const bounded = await plugin.spawnPaperFlow(
    process.execPath,
    "",
    childRoot,
    [
      "-e",
      "process.stdout.write('token=abcdefghijklmnop\\n' + 'x'.repeat(24000))"
    ],
    { action: "bounded-output", timeoutSeconds: 5 }
  );
  assert.ok(bounded.stdout.length <= 16000);
  const fullLog = fs.readFileSync(bounded.logPath, "utf8");
  assert.match(fullLog, /token=\[REDACTED\]/);
  assert.ok(fullLog.length > 16000);
  assert.equal(
    path.relative(path.join(childRoot, ".paperflow", "logs", "automation"), bounded.logPath).startsWith(".."),
    false
  );

  const binary = await plugin.spawnPaperFlow(
    process.execPath,
    "",
    childRoot,
    ["-e", "process.stdout.write(Buffer.from([0,1,2,3,4,5]))"],
    { action: "binary-output", timeoutSeconds: 5 }
  );
  const binaryLog = fs.readFileSync(binary.logPath, "utf8");
  assert.match(binaryLog, /binary output omitted/);
  assert.ok(!binaryLog.includes("\u0000"));

  const maximum = AutomationPlugin.__test.AUTOMATION_LOG_MAX_BYTES;
  const oversized = await plugin.spawnPaperFlow(
    process.execPath,
    "",
    childRoot,
    ["-e", `process.stdout.write('x'.repeat(${maximum * 2}))`],
    { action: "bounded-log", timeoutSeconds: 10 }
  );
  assert.ok(fs.statSync(oversized.logPath).size <= maximum);

  const activePromise = plugin.spawnPaperFlow(
    process.execPath,
    "",
    childRoot,
    ["-e", "setTimeout(() => {}, 60000)"],
    { action: "cancel-test", timeoutSeconds: 5, gracefulMs: 50 }
  );
  await new Promise((resolve) => setTimeout(resolve, 100));
  await assert.rejects(
    plugin.spawnPaperFlow(
      process.execPath,
      "",
      childRoot,
      ["-e", "process.exit(0)"],
      { action: "overlap", timeoutSeconds: 5 }
    ),
    /already running/
  );
  assert.equal(await plugin.cancelActiveJob("user"), true);
  const cancelled = await activePromise;
  assert.equal(cancelled.cancelled, true);
  assert.equal(cancelled.code, 130);
  assert.equal(plugin.activeChild, null);

  const unloadPromise = plugin.spawnPaperFlow(
    process.execPath,
    "",
    childRoot,
    ["-e", "setTimeout(() => {}, 60000)"],
    { action: "unload-test", timeoutSeconds: 5, gracefulMs: 50 }
  );
  await new Promise((resolve) => setTimeout(resolve, 100));
  plugin.onunload();
  const unloaded = await unloadPromise;
  assert.equal(unloaded.abortReason, "unload");
  assert.equal(plugin.activeChild, null);

  console.log("PaperFlow Automation lifecycle tests passed");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
