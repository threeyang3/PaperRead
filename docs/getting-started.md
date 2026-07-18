# Getting started

```powershell
uv tool install paperflow
paperflow init --vault "D:/Obsidian/MyResearch"
paperflow doctor
paperflow paper add "https://arxiv.org/abs/2607.12345"
```

Initialization asks for timezone, language, research profile, AI provider and
model, path layout, Form Flow, Bases, Obsidian automation, Public Feed, PDF
downloads, and AI fallback. Non-interactive initialization accepts a validated
configuration overlay.

PaperFlow never translates the original paper text merely because Obsidian is
Chinese. It localizes application UI and generated explanatory sections.
When a local PDF contains recognizable `Figure`/`Fig.` captions, import also
builds a local visual guide that prioritizes architecture and overview figures.
