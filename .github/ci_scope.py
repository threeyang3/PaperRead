"""Select CI scope from the entire push/PR diff; unknown paths require full checks."""

import os
import re
import subprocess
from pathlib import Path


def is_document(path):
    return path.startswith("docs/") or path in {
        "README.md",
        "CHANGELOG.md",
        "AGENTS.md",
        "CLAUDE.md",
        "LICENSE",
        "LICENSE.md",
    }


def classify(paths):
    code = [path for path in paths if not is_document(path)]
    # Application/resource changes still run ALL Python tests, coverage and audit.
    # OS integration, lockfiles, packaging/toolchains and unknown paths need the matrix.
    compatibility = (
        "src/paperflow/paths/",
        "src/paperflow/security/",
        "src/paperflow/data/",
        "src/paperflow/zotero/",
        "src/paperflow/database.py",
        "src/paperflow/utils.py",
        "src/paperflow/clock.py",
        "src/paperflow/doctor.py",
        "src/paperflow/cli.py",
        "src/paperflow/update_manager.py",
        "src/paperflow/feed/git_ops.py",
        "src/paperflow/sync_safety.py",
        "src/paperflow/migration",
        "src/paperflow/entity_migration",
        "tests/compatibility/",
        "tests/migration/",
        "tests/packaging/",
        "integrations/",
    )
    routine = ("src/", "tests/", "schemas/", "templates/", "prompts/", "taxonomy/", "examples/")
    full = any(path.startswith(compatibility) or not path.startswith(routine) for path in code)
    return {"code": bool(code), "full": full, "docs": bool(paths) and not code}


def git(*args):
    return subprocess.check_output(["git", *args])


def changed_paths(event, base, head):
    if not re.fullmatch(r"[0-9a-f]{40}", head or ""):
        raise ValueError("Missing or invalid head SHA")
    if not re.fullmatch(r"[0-9a-f]{40}", base or ""):
        raise ValueError("Missing or invalid base SHA")
    if base == "0" * 40:
        raw = git("ls-tree", "-r", "--name-only", "-z", head)
    else:
        if event == "pull_request":
            base = git("merge-base", base, head).decode().strip()
        # No rename detection: both old and new paths must affect scope.
        raw = git("diff", "--no-renames", "--name-only", "-z", base, head)
        git("diff", "--check", base, head)
    return [os.fsdecode(path) for path in raw.split(b"\0") if path]


def main():
    event = os.environ["CI_EVENT"]
    if event == "workflow_dispatch" or os.environ.get("CI_REF", "").startswith("refs/tags/"):
        result = {"code": True, "full": True, "docs": False}
    elif event in {"push", "pull_request"}:
        result = classify(changed_paths(event, os.environ["CI_BASE"], os.environ["CI_HEAD"]))
    else:
        raise ValueError(f"Unsupported CI event: {event}")
    output = "".join(f"{key}={str(value).lower()}\n" for key, value in result.items())
    print(output, end="")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as handle:
        handle.write(output)


if __name__ == "__main__":
    main()
