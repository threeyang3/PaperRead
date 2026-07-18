# Troubleshooting

Run these in order:

```text
paperflow config doctor
paperflow doctor
paperflow workspace validate
paperflow paths validate
paperflow migrate status
paperflow integration status form-flow
```

If configuration is invalid, the error identifies the field, current value,
and file to edit. If data is newer than the installed reader, upgrade the
application rather than forcing a write. If migration fails, inspect
`.paperflow/state/migrations/history.jsonl`; the run snapshot remains under
`.paperflow/backups`.

For Form Flow conflicts, review the existing file and its `.new` candidate.
PaperFlow deliberately does not overwrite the customized file.

If a visual guide is missing, confirm the paper has a local PDF, run
`paperflow paper visuals <paper_uid>`, then run `paperflow validate`. A
`no-captioned-figures` result means no reliable `Figure`/`Fig.` caption was
found; PaperFlow intentionally does not fabricate a diagram.

If an architecture figure is incomplete or a crop includes adjacent text, open
the PDF-page link below the image to compare it with the source, then rerun with
`--max-assets 6` after upgrading. Extracted images are Derived, so rerunning is
safe and does not overwrite User Data.
