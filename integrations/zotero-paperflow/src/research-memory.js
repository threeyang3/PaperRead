/* global Zotero, IOUtils, PathUtils */
"use strict";
// Loaded only on the explicit menu action. No Core connection is needed.
globalThis.PaperFlowOpenResearch = async function (options) {
  const M = globalThis.PaperFlowResearchModel;
  const S = globalThis.PaperFlowResearchStorage;
  const Panel = globalThis.PaperFlowResearchPanel;
  const win = Zotero.getMainWindow(), doc = win.document;
  if (globalThis.PaperFlowResearchClose) globalThis.PaperFlowResearchClose();
  if (typeof IOUtils === "undefined" || typeof PathUtils === "undefined") throw new Error("Zotero IOUtils/PathUtils unavailable");
  const data = Zotero.getDataDirectory().path;
  const root = PathUtils.join(data, "paperflow-research-private");
  const journal = new S.Journal(new S.MozillaFiles(IOUtils, PathUtils, root));
  const host = doc.createElementNS("http://www.w3.org/1999/xhtml", "aside");
  host.setAttribute("role", "dialog"); host.setAttribute("aria-label", "PaperFlow 研究记忆");
  host.style.cssText = "position:fixed;inset:6% 8%;z-index:2147483647;overflow:auto;padding:24px;background:Canvas;color:CanvasText;border:1px solid GrayText;border-radius:12px;font:menu;";
  const close = doc.createElementNS("http://www.w3.org/1999/xhtml", "button");
  close.textContent = "关闭研究记忆";
  const content = doc.createElementNS("http://www.w3.org/1999/xhtml", "div"); host.append(close, content);
  (doc.body || doc.documentElement).appendChild(host);
  let mounted;
  const cleanup = () => { mounted?.close(); host.remove(); win.removeEventListener("unload", cleanup);
    close.removeEventListener("click", cleanup); globalThis.PaperFlowResearchClose = null; };
  close.addEventListener("click", cleanup); win.addEventListener("unload", cleanup, {once: true});
  try {
    mounted = Panel.mount(content, {store: new M.Store(journal), journal,
      notify: options.notify, confirm: text => Promise.resolve(options.confirm(text)),
      initialPaper: options.paper_uid || "", initialTitle: options.title || "",
      save: async (name, text) => {
        M.assert(/^paperflow-[a-z0-9-]+\.(json|md)$/.test(name), "invalid generated export filename");
        const directory = PathUtils.join(data, "paperflow-research-exports");
        await IOUtils.makeDirectory(directory, {permissions: 0o700});
        const target = PathUtils.join(directory, name);
        // Explicit, immutable export: never overwrite an existing note.
        await IOUtils.writeUTF8(target, text, {mode: "create", flush: true});
        options.notify(`已导出 ${target}。私人会话请勿加入公开仓库。`);
      }});
    globalThis.PaperFlowResearchClose = cleanup;
  } catch (e) { cleanup(); throw e; }
};
