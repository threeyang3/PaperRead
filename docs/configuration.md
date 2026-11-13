# Configuration

Configuration precedence, lowest to highest:

1. application defaults;
2. `.paperflow/workspace.yaml`;
3. `.paperflow/workspace.local.yaml`;
4. `PAPERFLOW__SECTION__FIELD` environment variables;
5. explicit CLI overrides.

All resolved values are validated by strict Pydantic models. Unknown fields,
absolute Vault-specific roots, and parent traversal are rejected with the
field, current value, and repair location.

Keep machine choices and private subscription URLs in
`workspace.local.yaml`, which is ignored by Git. Plaintext tokens, passwords,
cookies, secrets, and API keys are rejected by `paperflow config set`.

Use `config show`, `show --resolved`, `validate`, `set`, `unset`,
`export-example`, and `doctor` to inspect and maintain configuration.

`obsidian.scheduler_owner` defaults to `obsidian`. Set it to `core` for
independent daily/Inbox/subscription scheduling while the local Core is
running. Time uses Asia/Shanghai. The existing Obsidian automation enable
switch and subscription interval remain effective. Login startup is opt-in
with `zotero service autostart --apply`; it uses the current Python environment
and current Windows user, so reapply it after moving the vault or its venv.
