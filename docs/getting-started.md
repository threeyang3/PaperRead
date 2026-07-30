# Getting started

Use the ordered [documentation map](README.md) for the full set of current
guides. For a complete Chinese walkthrough for both end users and project
maintainers, see [PaperFlow 用户与维护者指南](维护者与用户指南.md).

```powershell
uv tool install paperflow
paperflow init --vault "D:/Obsidian/MyResearch"
paperflow doctor
paperflow paper add "https://arxiv.org/abs/2607.12345"
```

Choose the primary reading front end after initialization:

- Zotero 9+: install `integrations/zotero-paperflow`, start the loopback Core,
  pair once, and use Zotero for bibliographic data, PDFs, and Reader annotations.
- Obsidian: enable PaperFlow Automation and Form Flow, then use the Control
  Center, Bases, and native/PDF++ reading workspace.

Both can run together. Obsidian remains the primary AI/User-note projection;
Zotero Reader annotations remain the editable annotation truth.

Initialization asks for timezone, language, research profile, AI provider and
model, path layout, Form Flow, Bases, Obsidian automation, Public Feed, PDF
downloads, and AI fallback. Non-interactive initialization accepts a validated
configuration overlay.

PaperFlow never translates the original paper text merely because Obsidian is
Chinese. It localizes application UI and generated explanatory sections.
When a local PDF contains recognizable `Figure`/`Fig.` captions, import also
builds a local visual guide that prioritizes architecture and overview figures.
Template v6 adaptively selects traceable figures grouped into architecture/method,
experiments/results, and task/hardware sections, with 12 only as a safety
ceiling. Captions stay in the original
language and collapse by default; every figure links back to its PDF page.

The official public data source is separate from the application repository:

```powershell
paperflow source add https://github.com/threeyang3/ArXiv-data.git --name arxiv-data
paperflow source inspect arxiv-data
paperflow source sync arxiv-data --dry-run
paperflow source sync arxiv-data
```
