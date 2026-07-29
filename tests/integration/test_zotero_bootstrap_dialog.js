const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(
  path.resolve(__dirname, "../../integrations/zotero-paperflow/bootstrap.js"),
  "utf8"
);

const prompts = [];
const alerts = [];
const windowMock = {
  prompt(message, initial) {
    prompts.push({ message, initial });
    return "  connected-value  ";
  },
  alert(message) {
    alerts.push(message);
  },
};
const sandbox = {
  console,
  ChromeUtils: {
    importESModule() { throw new Error("Services import unavailable"); },
    import() { throw new Error("legacy Services import unavailable"); },
  },
  Zotero: {
    getMainWindow() { return windowMock; },
  },
};
vm.createContext(sandbox);
vm.runInContext(source, sandbox, { filename: "bootstrap.js" });

assert.equal(
  sandbox.promptValue("PaperFlow Core", "请输入地址", "http://127.0.0.1:23140"),
  "connected-value"
);
assert.equal(prompts.length, 1);
assert.equal(prompts[0].initial, "http://127.0.0.1:23140");
sandbox.notify("fallback alert");
assert.equal(alerts.length, 1);
assert.ok(alerts[0].includes("fallback alert"));

console.log("PaperFlow Zotero bootstrap dialog fallback tests passed");

const nativePrompts = [];
const nativeAlerts = [];
const nativePromptService = {
  prompt(_parent, title, message, input) {
    nativePrompts.push({ title, message, initial: input.value });
    input.value = "  native-value  ";
    return true;
  },
  alert(_parent, title, message) {
    nativeAlerts.push({ title, message });
  },
};
const nativeSandbox = {
  console,
  ChromeUtils: {
    importESModule() { throw new Error("Services import unavailable"); },
    import() { throw new Error("legacy Services import unavailable"); },
  },
  Components: {
    classes: {
      "@mozilla.org/embedcomp/prompt-service;1": {
        getService() { return nativePromptService; },
      },
    },
    interfaces: { nsIPromptService: {} },
  },
  Zotero: {
    debug() {},
    getMainWindow() { return {}; },
  },
};
vm.createContext(nativeSandbox);
vm.runInContext(source, nativeSandbox, { filename: "bootstrap-native.js" });
assert.equal(
  nativeSandbox.promptValue("PaperFlow Core", "请输入令牌", ""),
  "native-value"
);
nativeSandbox.notify("native alert");
assert.equal(nativePrompts.length, 1);
assert.equal(nativeAlerts.length, 1);
assert.equal(nativeAlerts[0].title, "PaperFlow");
assert.ok(source.includes("PaperFlow：连接 Core"));
assert.ok(source.includes("PaperFlow：从 Core 导入论文及 PDF"));
assert.ok(source.includes("scheduleProjectionJob"));
assert.ok(source.includes("已复用既有分析并开始双端呈现"));
assert.ok(source.includes("Core 未接受 Zotero mapping"));
assert.ok(source.includes("以后 Core 重启会自动续期会话"));

console.log("PaperFlow Zotero native prompt service tests passed");

class LoadedCoreClient {}
const loaderSandbox = {
  console,
  __SCRIPT_URI_SPEC__: "file:///plugin/bootstrap.js",
  ChromeUtils: {
    importESModule() {
      return {
        Services: {
          io: {
            newURI(spec) {
              return { spec, pathQueryRef: "/plugin/bootstrap.js" };
            },
          },
          scriptloader: {
            loadSubScript(_spec, scope) {
              scope.PaperFlowCoreClient = LoadedCoreClient;
            },
          },
        },
      };
    },
  },
  Zotero: {
    debug() {},
    getMainWindow() { return {}; },
  },
};
vm.createContext(loaderSandbox);
vm.runInContext(source, loaderSandbox, { filename: "bootstrap-loader.js" });
const loaded = loaderSandbox.loadCoreClient();
assert.equal(loaded, LoadedCoreClient);
assert.ok(new loaded() instanceof LoadedCoreClient);

console.log("PaperFlow Zotero Core client loader tests passed");

class XpcomLoadedCoreClient {}
const xpcomPrompt = {
  prompt() { return false; },
  alert() {},
};
const xpcomLoaderSandbox = {
  console,
  __SCRIPT_URI_SPEC__: "file:///plugin/bootstrap.js",
  ChromeUtils: {
    importESModule() { throw new Error("ESM unavailable"); },
    import() { throw new Error("legacy import removed"); },
  },
  Components: {
    classes: {
      "@mozilla.org/network/io-service;1": {
        getService() {
          return {
            newURI(spec) { return { spec, pathQueryRef: "/plugin/bootstrap.js" }; },
          };
        },
      },
      "@mozilla.org/moz/jssubscript-loader;1": {
        getService() {
          return {
            loadSubScript(_spec, scope) {
              scope.PaperFlowCoreClient = XpcomLoadedCoreClient;
            },
          };
        },
      },
      "@mozilla.org/embedcomp/prompt-service;1": {
        getService() { return xpcomPrompt; },
      },
    },
    interfaces: {
      nsIIOService: {},
      mozIJSSubScriptLoader: {},
      nsIPromptService: {},
    },
  },
  Zotero: {
    debug() {},
    getMainWindow() { return {}; },
  },
};
vm.createContext(xpcomLoaderSandbox);
vm.runInContext(source, xpcomLoaderSandbox, { filename: "bootstrap-xpcom-loader.js" });
const xpcomLoaded = xpcomLoaderSandbox.loadCoreClient();
assert.equal(xpcomLoaded, XpcomLoadedCoreClient);
assert.ok(new xpcomLoaded() instanceof XpcomLoadedCoreClient);

console.log("PaperFlow Zotero XPCOM subscript loader tests passed");

class RootUriCoreClient {}
const loadedUris = [];
const rootUriSandbox = {
  console,
  ChromeUtils: {
    importESModule() {
      return {
        Services: {
          scriptloader: {
            loadSubScript(spec, scope) {
              loadedUris.push(spec);
              scope.PaperFlowCoreClient = RootUriCoreClient;
            },
          },
        },
      };
    },
  },
  Zotero: {
    debug() {},
    getMainWindow() { return {}; },
  },
};
vm.createContext(rootUriSandbox);
vm.runInContext(source, rootUriSandbox, { filename: "bootstrap-root-uri.js" });
assert.equal(
  rootUriSandbox.rememberPluginRoot({ rootURI: "file:///plugin-root/" }),
  "file:///plugin-root/"
);
assert.equal(rootUriSandbox.loadCoreClient(), RootUriCoreClient);
assert.deepEqual(loadedUris, ["file:///plugin-root/src/core-client.js"]);

console.log("PaperFlow Zotero rootURI subscript loader tests passed");
