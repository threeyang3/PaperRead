"use strict";
const {Modal, Notice} = require("obsidian");
const M = require("./research-memory/model.js");
const {Journal, NodeFiles} = require("./research-memory/storage.js");
const {mount} = require("./research-memory/panel.js");
const path = require("node:path");
const os = require("node:os");
class ResearchModal extends Modal {
  constructor(app, options) { super(app); this.options = options; }
  onOpen() { this.panel = mount(this.contentEl, this.options); }
  onClose() { this.panel?.close(); this.panel = null; }
}
async function open(plugin) {
  plugin.researchModal?.close();
  const vault = plugin.app.vault;
  if (!vault.adapter?.getBasePath) throw new Error("Research Memory currently requires a desktop vault");
  const namespace = (await M.digest(vault.adapter.getBasePath())).slice(0, 32);
  // Intentionally outside the Vault: raw prompts/quotes must not be silently
  // included in Obsidian Git, public feed exports, or generic Vault sync.
  const directory = path.join(os.homedir(), ".paperflow-private", "research", namespace);
  const journal = new Journal(new NodeFiles(directory));
  const file = plugin.app.workspace.getActiveFile();
  const metadata = file ? plugin.app.metadataCache.getFileCache(file)?.frontmatter || {} : {};
  const modal = new ResearchModal(plugin.app, {store: new M.Store(journal), journal,
    initialPaper: metadata.paper_uid || "", initialTitle: metadata.paper_title || file?.basename || "",
    notify: value => new Notice(value, 12000),
    confirm: text => Promise.resolve(window.confirm(text)),
    save: async (name, text) => {
      M.assert(/^paperflow-[a-z0-9-]+\.(json|md)$/.test(name), "invalid generated export filename");
      const folder = "PaperFlow Research Exports";
      if (!await vault.adapter.exists(folder)) {
        try { await vault.createFolder(folder); } catch (e) { if (!await vault.adapter.exists(folder)) throw e; }
      }
      // Vault.create refuses to replace an existing user-edited note.
      const file = await vault.create(`${folder}/${name}`, text);
      new Notice(`已导出 ${file.path}；私人会话请勿加入公开仓库`, 10000);
    }});
  plugin.researchModal = modal; modal.open();
}
module.exports = {open, ResearchModal};
