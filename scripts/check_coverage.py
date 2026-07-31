from __future__ import annotations

import json
import sys
from pathlib import Path


MINIMUMS = {
    "src/paperflow/data/store.py": 90.0,
    "src/paperflow/feed/publisher.py": 80.0,
    "src/paperflow/pdf_resolver.py": 70.0,
    "src/paperflow/security/artifacts.py": 85.0,
    "src/paperflow/workspace_v3.py": 80.0,
    "src/paperflow/zotero/core_service.py": 65.0,
}


def main(path: str = "coverage.json") -> int:
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    files = {name.replace("\\", "/"): value for name, value in report.get("files", {}).items()}
    failures: list[str] = []
    for name, minimum in MINIMUMS.items():
        value = files.get(name)
        if value is None:
            failures.append(f"{name}: missing from coverage report")
            continue
        actual = float(value["summary"]["percent_covered"])
        if actual < minimum:
            failures.append(f"{name}: {actual:.2f}% < {minimum:.2f}%")
    if failures:
        print("Critical coverage gate failed:")
        print("\n".join(f"- {item}" for item in failures))
        return 1
    print("Critical coverage gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*(sys.argv[1:] or ["coverage.json"])))
