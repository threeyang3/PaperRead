"use strict";

function safePaperId(value) {
  const result = String(value || "").replace(":", "_");
  if (!/^[A-Za-z0-9._-]+$/.test(result)) {
    throw new Error("The active note has an unsafe paper_uid");
  }
  return result;
}

async function ensureMarkdown(app, path, content) {
  const normalized = path.replaceAll("\\", "/");
  let file = app.vault.getAbstractFileByPath(normalized);
  if (file) return file;
  const parent = normalized.split("/").slice(0, -1).join("/");
  if (parent) await app.vault.adapter.mkdir(parent).catch(() => {});
  return app.vault.create(normalized, content);
}

async function openReadingWorkspace(app, options = {}) {
  const paper = app.workspace.getActiveFile();
  if (!paper || paper.extension !== "md") {
    throw new Error("Open a generated PaperFlow paper note first");
  }
  const metadata = app.metadataCache.getFileCache(paper)?.frontmatter || {};
  if (metadata.type !== "paper" || !metadata.paper_uid || !metadata.paper_pdf_path) {
    throw new Error("The active note is not a PaperFlow paper with a local PDF");
  }
  const paperId = safePaperId(metadata.paper_uid);
  const year = String(metadata.paper_year || "Unclassified");
  const pdf = app.vault.getAbstractFileByPath(String(metadata.paper_pdf_path));
  if (!pdf) throw new Error(`Local PDF is missing: ${metadata.paper_pdf_path}`);

  const annotationPath = String(
    options.annotationPath || `60 Annotations/${paperId}/index.md`
  ).replaceAll("\\", "/");
  const reviewPath = `60 Reviews/${year}/${paperId}.review.md`;
  const communityPath = `70 Community/${year}/${paperId}.community.md`;
  const annotation = await ensureMarkdown(
    app,
    annotationPath,
    `---\ntype: paperflow-annotation-index-note\npaper_uid: ${metadata.paper_uid}\n---\n\n# 标注\n\nPDF++ 复制的标注链接可粘贴到这里；正式标注由 PaperFlow 命令同步。\n`
  );
  const review = await ensureMarkdown(
    app,
    reviewPath,
    `---\ntype: paperflow-user-paper-review\nschema_version: 1\nreview_id: review-${paperId}\npaper_uid: ${metadata.paper_uid}\nrating:\ncreated_at:\nupdated_at:\n---\n\n## 摘要\n\n## 优点\n\n## 局限\n\n## 问题\n\n## 复现笔记\n\n## 结论\n`
  );
  const community = await ensureMarkdown(
    app,
    communityPath,
    `---\ntype: paperflow-community-note\npaper_uid: ${metadata.paper_uid}\ncommunity_count: 0\n---\n\n# 社区观点\n\n> 社区订阅是只读缓存，不会写入个人标注或个人评审。\n`
  );

  const existingLeaf = file => app.workspace.getLeavesOfType?.(
    file.extension === "pdf" ? "pdf" : "markdown"
  )?.find(leaf => leaf.view?.file?.path === file.path);
  const pdfLeaf = existingLeaf(pdf) || app.workspace.getLeaf("split", "vertical");
  // PDF++ can leave openFile pending while its viewer loads. Open the other
  // panes immediately and bound the wait so the reading command stays usable.
  const pdfOpening = Promise.resolve(pdfLeaf.openFile(pdf)).then(
    () => ({ ready: true }), error => ({ error })
  );
  const annotationLeaf = existingLeaf(annotation) || app.workspace.getRightLeaf(false);
  if (!annotationLeaf) throw new Error("Unable to create the annotation leaf");
  await annotationLeaf.openFile(annotation);
  const reviewLeaf = existingLeaf(review) || app.workspace.createLeafBySplit(pdfLeaf, "horizontal");
  await reviewLeaf.openFile(review);
  const communityLeaf = existingLeaf(community) || app.workspace.getRightLeaf(true);
  if (!communityLeaf) throw new Error("Unable to create the Community leaf");
  await communityLeaf.openFile(community);
  await app.workspace.revealLeaf(annotationLeaf);
  await app.workspace.revealLeaf(communityLeaf);
  await app.workspace.revealLeaf(pdfLeaf);
  app.workspace.setActiveLeaf(pdfLeaf, { focus: true });
  let pdfTimer;
  const pdfState = await Promise.race([
    pdfOpening,
    new Promise(resolve => {
      pdfTimer = setTimeout(() => resolve({ ready: false }), options.pdfLoadTimeoutMs ?? 5000);
    })
  ]);
  clearTimeout(pdfTimer);
  if (pdfState.error) throw pdfState.error;
  return {
    paper: paper.path,
    pdf: pdf.path,
    annotation: annotation.path,
    review: review.path,
    community: community.path,
    ...(pdfState.ready ? {} : { pdfLoading: true })
  };
}

module.exports = { openReadingWorkspace, safePaperId };
