/* Explicit-action research panel shared by Zotero and Obsidian. MIT. */
(function (root, factory) {
  const common = typeof module === "object" && module.exports;
  const api = factory(common ? require("./model.js") : root.PaperFlowResearchModel,
    common ? require("./client.js") : root.PaperFlowResearchClient);
  if (common) module.exports = api; else root.PaperFlowResearchPanel = api;
})(globalThis, function (M, API) {
  "use strict";
  function mount(container, {store, journal, notify, confirm, save, initialPaper = "", initialTitle = ""}) {
    const doc = container.ownerDocument;
    let record = null, closed = false, active = null, offset = 0;
    const disposers = [];
    const renderDisposers = []; let rendering = false;
    const el = (tag, text, parent = container) => {
      const node = doc.createElementNS("http://www.w3.org/1999/xhtml", tag);
      if (text !== undefined) node.textContent = text;
      parent.appendChild(node); return node;
    };
    const field = (label, value = "", type = "text", parent = container) => {
      const wrap = el("label", label, parent), input = el(type === "textarea" ? "textarea" : "input", undefined, wrap);
      if (type !== "textarea") input.type = type;
      input.value = value; input.style.display = "block"; input.style.width = "100%";
      if (type === "textarea") { input.rows = 4; input.maxLength = M.LIMITS.text; }
      return input;
    };
    const button = (label, fn, parent = container) => {
      const node = el("button", label, parent); node.type = "button";
      const listener = async () => {
        if (closed || (active && label !== "取消网络请求")) return;
        node.disabled = true;
        try { await fn(); } catch (e) { if (!closed) notify(e.message || String(e)); }
        finally { if (!closed) node.disabled = false; }
      };
      node.addEventListener("click", listener); (rendering ? renderDisposers : disposers).push(() => node.removeEventListener("click", listener)); return node;
    };
    const need = () => { M.assert(record, "先建立或打开一个会话"); return record; };
    el("h2", "PaperFlow · 研究记忆");
    el("p", "本地私有记录；不启动 Agent CLI/Core，不自动上传或发布。引文匹配不等于论断已被证明。版本和定位由你核对。浏览器通道采用手动 JSON 文件回传。");
    const selector = el("select"); selector.style.maxWidth = "100%";
    const title = field("会话标题", initialTitle);
    const paper = field("论文稳定 ID（arxiv:2504.16054 或 doi:…）", initialPaper);
    const status = el("p", "尚未打开会话");
    const refresh = async () => {
      const page = await journal.list(50, offset);
      if (closed) return;
      selector.replaceChildren(); el("option", "选择会话…", selector).value = "";
      for (const item of page.items) el("option", `${item.title} · r${item.revision}`, selector).value = item.id;
      selector.value = record?.id || "";
    };
    const choose = async () => {
      if (closed || active || !selector.value) return;
      try { record = await store.read(selector.value); render(); } catch (e) { notify(e.message); }
    };
    selector.addEventListener("change", choose); disposers.push(() => selector.removeEventListener("change", choose));
    button("刷新（冲突后重读）", async () => { if (record) record = await store.read(record.id); await refresh(); render(); });
    button("上一页", async () => { offset = Math.max(0, offset - 50); await refresh(); });
    button("下一页", async () => { offset += 50; await refresh(); });
    button("建立会话", async () => { record = await store.create([paper.value], title.value); await refresh(); render(); });
    const contexts = el("section");
    el("h3", "明确提供给 AI 的材料");
    const kind = el("select"); for (const value of ["excerpt", "abstract", "user-note"]) el("option", value, kind).value = value;
    const version = field("原文版本（未核实可留空）"); const locator = field("页码 / 图号 / 标注定位");
    const excerpt = field("材料原文（只发送勾选的材料；不会自动读取整篇 PDF）", "", "textarea");
    button("保存材料快照", async () => {
      const r = need(); const value = await store.context(r.id, r.revision, {paper_uid: r.paper_uids[0],
        kind: kind.value, text: excerpt.value, version: version.value, locator: locator.value});
      record = value.record; excerpt.value = ""; render();
    });
    const messages = el("section"), requests = el("section"), insights = el("section");
    el("h3", "提问 / 记录");
    const question = field("问题（每次调用只包含此问题和勾选材料；历史对话不会隐式全量发送）", "", "textarea");
    const selectedContexts = () => [...contexts.querySelectorAll('input[type="checkbox"]:checked')].map(x => x.value);
    const selectedMessages = () => [...messages.querySelectorAll('input[type="checkbox"]:checked')].map(x => x.value);
    button("保存个人问题", async () => { const r = need(); record = (await store.message(r.id, r.revision,
      {role: "user", content: question.value, context_ids: selectedContexts()})).record; render(); });
    button("导出浏览器提问包", async () => {
      const r = need(); const result = await store.request(r.id, r.revision,
        {question: question.value, context_ids: selectedContexts(), provider: "browser", model: ""});
      record = result.record; render();
      await save(`paperflow-question-${result.result.request_id}.json`, M.encode(await store.requestPack(r.id, result.result.request_id)), "application/json");
    });
    const incoming = field("回传 / 私有会话 JSON（粘贴文件内容）", "", "textarea"); incoming.maxLength = M.LIMITS.bytes;
    button("导入浏览器回答", async () => {
      const r = need(); record = (await store.reply(r.id, r.revision, M.parse(incoming.value))).record;
      incoming.value = ""; render();
    });
    button("导入私有会话（不导入审批权限）", async () => {
      const data = M.parse(incoming.value);
      if (!await confirm("私有会话会写入此设备。外部待执行任务被移除、所有结论重新置为候选，是否继续？")) return;
      record = await store.importPrivate(data); incoming.value = ""; await refresh(); render();
    });
    const settings = el("details"); el("summary", "直接 API（密钥仅驻留本次窗口内存）", settings);
    const url = field("HTTPS Chat Completions 完整地址", "https://api.openai.com/v1/chat/completions", "text", settings);
    const model = field("模型名称（必须填写）", "", "text", settings);
    const credential = field("API Key（不写入本地配置或会话）", "", "password", settings);
    credential.autocomplete = "off";
    async function ask(distill) {
      const r = need(), key = credential.value, endpoint = M.endpoint(url.value), name = model.value;
      M.string(key, "API key", 4096); M.string(name, "model", 200);
      const contextIDs = selectedContexts(), messageIDs = selectedMessages();
      if (distill) API.distillationPrompt(r, messageIDs);
      else M.string(question.value, "问题", M.LIMITS.text);
      if (!await confirm(`将选定材料发送到 ${new URL(endpoint).origin}，模型 ${name}。可能产生费用；不含任何自动工具调用。继续？`)) return;
      const controller = new AbortController(); active = controller; selector.disabled = true;
      let requestID = null;
      try {
        let prompt;
        if (distill) prompt = API.distillationPrompt(r, messageIDs);
        else {
          const created = await store.request(r.id, r.revision,
            {question: question.value, context_ids: contextIDs, provider: "api", model: name});
          requestID = created.result.request_id; record = created.record;
          prompt = API.questionPrompt(await store.requestPack(r.id, requestID)); render();
        }
        const answer = await API.complete({url: endpoint, key, model: name, prompt, signal: controller.signal});
        if (closed || controller.signal.aborted) throw new Error("Request cancelled");
        const latest = await store.read(r.id);
        if (distill) {
          // Do not silently apply a result to a concurrently changed conversation.
          if (latest.revision !== r.revision) throw new M.ConflictError("会话已改变，请重新提炼；原始记录未修改");
          const value = M.parse(answer); M.strict(value, ["candidates"], "distillation output");
          record = (await store.propose(r.id, latest.revision, value.candidates)).record;
        } else {
          const pack = await store.requestPack(r.id, requestID);
          record = (await store.reply(r.id, latest.revision, {...pack.reply_contract, content: answer})).record;
        }
        render();
      } catch (error) {
        if (requestID) {
          const latest = await store.read(r.id);
          if (latest?.requests.find(q => q.id === requestID)?.state === "pending") {
            try { const value = await store.stop(r.id, latest.revision, requestID, controller.signal.aborted ? "cancelled" : "failed");
              if (!closed) record = value.record;
            } catch (_) { /* A concurrent writer owns the latest state; never overwrite it. */ }
          }
        }
        throw error;
      } finally { active = null; if (!closed) { selector.disabled = false; render(); } }
    }
    button("发送 API 问题", () => ask(false), settings);
    button("提炼勾选消息（仅生成候选）", () => ask(true), settings);
    button("取消网络请求", () => { active?.abort(); }, settings);
    button("导出私有会话 JSON", async () => { const r = need();
      if (await confirm("该文件包含私人问答及材料原文，不应提交公开仓库。确认导出？"))
        await save(`paperflow-private-${r.id}.json`, M.encode(await store.exportPrivate(r.id)), "application/json"); });
    button("导出版本化 Markdown", async () => { const r = await store.read(need().id);
      if (await confirm("Markdown 包含私人问答；保存新文件，不覆盖现有研究笔记。确认导出？"))
        await save(`paperflow-${r.id}-r${r.revision}.md`, M.markdown(r), "text/markdown"); });
    button("导出已审核公开结论", async () => {
      const value = await store.exportPublic(need().id);
      M.assert(value.insights.length, "尚无已审核公开文本；不会导出私有会话");
      if (await confirm(`仅导出 ${value.insights.length} 条明确审核的公开文本，仍请复核其中没有私人研究内容。`))
        await save(`paperflow-public-${record.id}.json`, M.encode(value), "application/json");
    });
    // No innerHTML, eval, or interpreted model HTML.
    function render() {
      if (closed) return;
      for (const dispose of renderDisposers.splice(0)) dispose();
      contexts.replaceChildren(); messages.replaceChildren(); requests.replaceChildren(); insights.replaceChildren();
      if (!record) return;
      rendering = true;
      status.textContent = `${record.title} · r${record.revision} · ${record.paper_uids.join(", ")}`;
      el("h3", "可选材料（每次提问显式勾选）", contexts);
      for (const c of record.contexts) {
        const row = el("label", `${c.kind} · ${c.version || "版本未核实"} · ${c.locator} · ${c.text.slice(0, 80)}`, contexts);
        const box = el("input", undefined, row); box.type = "checkbox"; box.value = c.id; el("br", "", contexts);
      }
      el("h3", "近期 20 条消息（完整历史在私有导出中）", messages);
      for (const m of record.messages.slice(-20)) {
        const detail = el("details", undefined, messages);
        const summary = el("summary", `${m.role} · ${m.status} · ${m.content.slice(0, 60)}`, detail);
        const box = el("input", undefined, summary); box.type = "checkbox"; box.value = m.id;
        el("pre", m.content, detail).style.whiteSpace = "pre-wrap";
      }
      el("h3", "任务状态", requests);
      for (const q of record.requests.slice(-10)) {
        const row = el("p", `${q.provider} · ${q.state} · ${q.id}`, requests);
        if (q.state === "pending") button("取消未完成任务", async () => {
          record = (await store.stop(record.id, record.revision, q.id)).record; render();
        }, row);
      }
      el("h3", "研究结论（AI 不得自行采纳或发布）", insights);
      for (const insight of record.insights) {
        const detail = el("details", undefined, insights);
        el("summary", `${insight.review} · ${insight.kind} · ${insight.claim.slice(0, 70)}`, detail);
        el("pre", insight.claim, detail).style.whiteSpace = "pre-wrap";
        for (const e of insight.evidence) el("pre", `引文仅匹配已供材料 ${e.context_id}：\n${e.quote}`, detail).style.whiteSpace = "pre-wrap";
        button("人工采纳", async () => {
          if (await confirm("请先核对来源和推断边界。引文匹配不代表论断属实。确认采纳？")) {
            record = (await store.review(record.id, record.revision, insight.id, "accepted", true)).record; render();
          }
        }, detail);
        button("退回候选", async () => { record = (await store.review(record.id, record.revision, insight.id, "candidate", true)).record; render(); }, detail);
        const publicText = field("可公开的重写文本（不会默认复制私人论断）", insight.publication_text, "textarea", detail);
        button("确认此文本可公开", async () => {
          if (await confirm("请确认此文本不含私人信息、未公开研究或未经许可的原文。仅保存公开导出许可，不会上传。")) {
            record = (await store.publication(record.id, record.revision, insight.id, publicText.value, true)).record; render();
          }
        }, detail);
      }
      rendering = false;
    }
    refresh().catch(e => { if (!closed) notify(e.message); });
    return {close() { closed = true; active?.abort(); credential.value = "";
      for (const dispose of [...disposers.splice(0), ...renderDisposers.splice(0)]) dispose(); container.replaceChildren(); }};
  }
  return {mount};
});
