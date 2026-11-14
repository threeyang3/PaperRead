/* Immutable revision journal. No shared mutable index, no silent recovery. MIT. */
(function (root, factory) {
  const model = typeof module === "object" && module.exports ? require("./model.js") : root.PaperFlowResearchModel;
  const api = factory(model);
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PaperFlowResearchStorage = api;
})(globalThis, function (M) {
  "use strict";
  const REVISION = /^[0-9]{8}\.json$/;
  const MAX_FILE = M.LIMITS.bytes + 1024;
  async function envelope(record) {
    const content = M.encode(record);
    return JSON.stringify({schema_version: 1, sha256: await M.digest(content), record});
  }
  async function decode(value, key, revision) {
    M.assert(new TextEncoder().encode(value).length <= MAX_FILE, "journal file too large");
    const wrapper = JSON.parse(value);
    M.strict(wrapper, ["schema_version", "sha256", "record"], "journal envelope");
    M.assert(wrapper.schema_version === 1 && wrapper.record, "invalid journal envelope");
    const content = M.encode(wrapper.record);
    M.assert(await M.digest(content) === wrapper.sha256, "journal checksum mismatch");
    const record = M.parse(content);
    M.assert(record.id === key && record.revision === revision, "journal identity/revision mismatch");
    return record;
  }
  class Journal {
    constructor(fs) { this.fs = fs; }
    async load(key) {
      M.id(key);
      const names = await this.fs.names(key);
      const revisions = names.filter(x => REVISION.test(x)).sort();
      if (!revisions.length) return null;
      const latest = revisions.at(-1);
      return decode(await this.fs.read(key, latest, MAX_FILE), key, Number(latest.slice(0, 8)));
    }
    async commit(key, expected, record) {
      M.id(key);
      M.assert(record.id === key && record.revision === expected + 1 && record.revision <= 99999999,
        "invalid journal revision");
      const current = await this.load(key);
      if ((current?.revision || 0) !== expected) throw new M.ConflictError("Journal changed; reload before writing");
      await this.fs.create(key, `${String(record.revision).padStart(8, "0")}.json`, await envelope(record));
    }
    async list(limit = 50, offset = 0) {
      M.assert(Number.isInteger(limit) && limit > 0 && limit <= 100 && Number.isInteger(offset) && offset >= 0, "invalid list window");
      // Pagination reads names first, not every conversation body.
      const keys = (await this.fs.names("")).filter(key => /^[a-f0-9]{32}$/.test(key)).sort();
      const window = keys.slice(offset, offset + limit);
      const items = [];
      for (const key of window) {
        const r = await this.load(key);
        if (r) items.push({id: r.id, title: r.title, paper_uids: r.paper_uids, revision: r.revision, updated_at: r.updated_at});
      }
      return {items, next: offset + limit < keys.length ? offset + limit : null};
    }
  }
  class NodeFiles {
    constructor(root) { this.fs = require("node:fs/promises"); this.path = require("node:path"); this.root = this.path.resolve(root); }
    async directory(key) {
      if (key) M.id(key);
      await this.fs.mkdir(this.root, {recursive: true, mode: 0o700});
      // Resolve root once per call. Reject a root symlink and record-directory
      // symlinks; record IDs are generated, never a user-controlled path.
      M.assert(!(await this.fs.lstat(this.root)).isSymbolicLink(), "journal root must not be a symlink");
      if (!key) return this.root;
      const dir = this.path.join(this.root, key);
      try { await this.fs.mkdir(dir, {mode: 0o700}); } catch (e) { if (e.code !== "EEXIST") throw e; }
      const stat = await this.fs.lstat(dir);
      M.assert(stat.isDirectory() && !stat.isSymbolicLink(), "invalid journal directory");
      return dir;
    }
    async names(key) { return this.fs.readdir(await this.directory(key)); }
    async read(key, name, max) {
      M.assert(REVISION.test(name), "invalid revision filename");
      const file = this.path.join(await this.directory(key), name);
      const stat = await this.fs.lstat(file);
      M.assert(stat.isFile() && !stat.isSymbolicLink() && stat.size <= max, "invalid journal file");
      const constants = require("node:fs").constants;
      const handle = await this.fs.open(file, constants.O_RDONLY | (constants.O_NOFOLLOW || 0));
      try {
        const actual = await handle.stat(); M.assert(actual.size <= max, "journal file grew beyond limit");
        const bytes = Buffer.alloc(max + 1); const {bytesRead} = await handle.read(bytes, 0, bytes.length, 0);
        M.assert(bytesRead <= max, "journal file too large");
        return new TextDecoder("utf-8", {fatal: true}).decode(bytes.subarray(0, bytesRead));
      } finally { await handle.close(); }
    }
    async create(key, name, content) {
      M.assert(REVISION.test(name), "invalid revision filename");
      const dir = await this.directory(key);
      const temporary = this.path.join(dir, `.pending-${M.token()}`);
      const target = this.path.join(dir, name);
      const file = await this.fs.open(temporary, "wx", 0o600);
      try { await file.writeFile(content, "utf8"); await file.sync(); } finally { await file.close(); }
      try {
        // Hard-link publish is atomic and refuses an existing revision.
        await this.fs.link(temporary, target);
      } catch (error) {
        if (error.code === "EEXIST") throw new M.ConflictError("Concurrent journal write; reload");
        throw error;
      } finally { await this.fs.unlink(temporary).catch(() => {}); }
    }
  }
  class MozillaFiles {
    constructor(IO, Path, root) { this.io = IO; this.path = Path; this.root = root; }
    async directory(key) {
      if (key) M.id(key);
      await this.io.makeDirectory(this.root, {permissions: 0o700});
      const check = async path => {
        const stat = await this.io.stat(path);
        M.assert(stat.type === "directory", "invalid journal directory (symlinks are not supported)");
      };
      await check(this.root);
      if (!key) return this.root;
      const dir = this.path.join(this.root, key);
      await this.io.makeDirectory(dir, {permissions: 0o700}); await check(dir); return dir;
    }
    async names(key) { return (await this.io.getChildren(await this.directory(key))).map(p => this.path.filename(p)); }
    async read(key, name, max) {
      M.assert(REVISION.test(name), "invalid revision filename");
      const file = this.path.join(await this.directory(key), name);
      const stat = await this.io.stat(file);
      M.assert(stat.type === "regular" && stat.size <= max, "invalid journal file");
      const bytes = await this.io.read(file, {maxBytes: max + 1});
      M.assert(bytes.length <= max, "journal file too large");
      return new TextDecoder("utf-8", {fatal: true}).decode(bytes);
    }
    async create(key, name, content) {
      M.assert(REVISION.test(name), "invalid revision filename");
      const dir = await this.directory(key);
      const tmp = this.path.join(dir, `.pending-${M.token()}`);
      const target = this.path.join(dir, name);
      await this.io.writeUTF8(tmp, content, {mode: "create", flush: true});
      try { await this.io.move(tmp, target, {noOverwrite: true}); }
      catch (e) {
        if (e.name === "NoModificationAllowedError") throw new M.ConflictError("Concurrent journal write; reload");
        throw e;
      } finally { await this.io.remove(tmp, {ignoreAbsent: true}).catch(() => {}); }
    }
  }
  return {Journal, NodeFiles, MozillaFiles};
});
