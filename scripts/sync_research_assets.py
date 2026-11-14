"""Copy shared JS into self-contained plugin packages; --check never writes."""
from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ("model.js", "storage.js", "client.js", "panel.js")
TARGETS = ("integrations/obsidian-paperflow-automation/research-memory",
           "integrations/zotero-paperflow/research-memory")


def sync(check: bool = False) -> None:
    for target in TARGETS:
        for name in ASSETS:
            source = ROOT / "integrations/shared/research-memory" / name
            dest = ROOT / target / name
            content = source.read_bytes()
            if check:
                if not dest.is_file() or dest.read_bytes() != content:
                    raise SystemExit(f"Shared research asset is stale: {dest.relative_to(ROOT)}")
            elif not dest.is_file() or dest.read_bytes() != content:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    sync(parser.parse_args().check)
