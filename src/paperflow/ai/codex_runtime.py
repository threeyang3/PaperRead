from __future__ import annotations

import os
from pathlib import Path


CODEX_ISOLATION_ARGS = [
    "--ephemeral",
    "--ignore-user-config",
    "--ignore-rules",
    "--disable",
    "plugins",
    "--disable",
    "remote_plugin",
    "--config",
    "shell_environment_policy.inherit=none",
]


def isolated_codex_environment(temporary_root: Path) -> dict[str, str]:
    """Return the existing process environment without touching credentials.

    Codex itself may use its normal authenticated CLI session. PaperFlow never
    opens, copies, rewrites, or relocates Codex credential files.
    """
    temporary_root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PAPERFLOW_STAGED_INPUT"] = str(temporary_root)
    return env
