# Obsidian Form Flow integration

This versioned bundle keeps `form-flow` as PaperFlow's manual paper-entry UI.
It requires official Form Flow 0.0.8 or newer and creates request files only;
it never executes paper-provided code.

Install or inspect it with:

```text
paperflow integration install form-flow
paperflow integration status form-flow
paperflow integration repair form-flow
paperflow integration upgrade form-flow
```

User-modified forms are never overwritten. A conflicting bundled update is
written as `<filename>.new`, and the existing file is retained for review.
