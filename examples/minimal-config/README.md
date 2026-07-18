# Minimal configuration

Initialize a clean temporary Vault without prompts:

```powershell
paperflow init --vault ".\My Vault" --non-interactive --config workspace.yaml
```

The file is an overlay on validated built-in defaults, so omitted fields keep
safe defaults.
