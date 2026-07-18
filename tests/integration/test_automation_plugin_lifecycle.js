"use strict";

const assert = require("node:assert/strict");
const Module = require("node:module");

let layoutReady;
const vaultEvents = [];
const registeredEvents = [];
const registeredIntervals = [];
const registeredViews = [];
const ribbonIcons = [];
const saved = [];
const openedLinks = [];
let revealedLeaf = null;

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
        }
      },
      vault: {
        adapter: {
          getBasePath() {
            return process.cwd();
          }
        },
        on(name, callback) {
          vaultEvents.push({ name, callback });
          return { name };
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

  addCommand() {}
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
class Modal {}

const originalLoad = Module._load;
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
  const AutomationPlugin = require(
    "../../integrations/obsidian-paperflow-automation/main.js"
  );
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
  global.localStorage = { getItem: () => "en" };
  assert.equal(AutomationPlugin.__test.isChinese(), false);
  assert.equal(AutomationPlugin.__test.text("中文", "English"), "English");
  const plugin = new AutomationPlugin();
  plugin.writeLocaleMarker = async () => {};
  plugin.checkDaily = async () => {};
  plugin.runJob = async () => {};

  await plugin.onload();
  assert.equal(typeof layoutReady, "function");
  layoutReady();
  await new Promise((resolve) => setImmediate(resolve));

  assert.deepEqual(
    vaultEvents.map((event) => event.name),
    ["create", "modify", "rename"]
  );
  assert.equal(registeredEvents.length, 3);
  assert.equal(registeredIntervals.length, 2);
  assert.equal(registeredViews.length, 1);
  assert.equal(registeredViews[0].type, "paperflow-control-center");
  assert.equal(ribbonIcons.length, 1);
  const view = registeredViews[0].factory({ app: plugin.app });
  await view.onOpen();
  assert.equal(view.contentEl.findByClass("paperflow-control-hero").length, 1);
  assert.equal(view.contentEl.findByClass("paperflow-automation-grid").length, 1);
  assert.equal(view.contentEl.findByClass("paperflow-automation-track").length, 3);
  assert.equal(view.contentEl.findByClass("paperflow-task-shelf").length, 1);
  assert.equal(view.contentEl.findByClass("paperflow-task-entry").length, 6);
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
  assert.equal(saved.length, 1);
  assert.equal(saved[0].inboxEventDebounceMs, 1500);
  assert.equal(saved[0].openControlCenterOnStartup, true);
  assert.equal(revealedLeaf.state.type, "paperflow-control-center");
  assert.equal(revealedLeaf.state.active, true);
  assert.equal(plugin.started, true);
  assert.equal(AutomationPlugin.__test.intervalDue("", 60), true);
  console.log("PaperFlow Automation lifecycle tests passed");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
