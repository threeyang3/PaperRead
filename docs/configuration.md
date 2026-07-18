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
