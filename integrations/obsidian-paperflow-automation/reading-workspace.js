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

async function openReadingWorkspace(app) {
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

  const annotationPath = `60 Annotations/${year}/${paperId}/index.md`;
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

  const pdfLeaf = app.workspace.getLeaf("split", "vertical");
  await pdfLeaf.openFile(pdf);
  const annotationLeaf = app.workspace.getRightLeaf(false);
  await annotationLeaf.openFile(annotation);
  const reviewLeaf = app.workspace.getLeaf("split", "horizontal");
  await reviewLeaf.openFile(review);
  const communityLeaf = app.workspace.getRightLeaf(true);
  await communityLeaf.openFile(community);
  app.workspace.revealLeaf(pdfLeaf);
  return {
    paper: paper.path,
    pdf: pdf.path,
    annotation: annotation.path,
    review: review.path,
    community: community.path
  };
}

module.exports = { openReadingWorkspace, safePaperId };
