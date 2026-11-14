"""Local-only, non-CI validation. Never calls GitHub, pip or an AI provider."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    commands = [
        [sys.executable, "scripts/sync_research_assets.py", "--check"],
        ["node", "--test", *[str(p.relative_to(ROOT)) for p in sorted((ROOT / "tests/research_memory").glob("*.test.cjs"))]],
        [sys.executable, "-m", "pytest", "tests/research_memory/test_api_review.py"],
        [sys.executable, "-m", "compileall", "-q", "src", "scripts"],
    ]
    for command in commands:
        print("LOCAL:", " ".join(command), flush=True)
        subprocess.run(command, cwd=ROOT, env=env, check=True)


if __name__ == "__main__":
    main()
