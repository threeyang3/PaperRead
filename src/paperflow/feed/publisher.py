from __future__ import annotations

import hashlib
import json
import re
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from paperflow.versioning import APPLICATION_VERSION, VERSIONS, check_reader_version
from paperflow.workspace import WorkspaceSettings, dump_yaml
from paperflow.clock import WorkspaceClock, parse_aware_datetime
from paperflow.security.artifacts import PublishScanner
from paperflow.security.paths import (
    assert_distinct_storage_components,
    encode_storage_component_v2,
    resolve_under,
    safe_storage_component,
)
from paperflow.data.records import PublicRawPaperRecord, RawPaperRecord
from paperflow.utils import atomic_json
import zstandard


ABSOLUTE_PATH_RE = re.compile(
    r"(?i)(?:(?<![A-Za-z0-9])[A-Z]:[\\/](?:Users[\\/])?|"
    r"/home/|/Users/|\\\\[^\\]+\\)"
)
SECRET_RE = re.compile(
    r"(?i)(?:token|cookie|password|authorization|api[_-]?key)"
    r"[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_\-./+]{8,}"
)
FORBIDDEN_NAMES = {
    "paperflow.db",
    "auth.json",
    ".env",
}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".log", ".pdf"}
FEED_TEXT_SUFFIXES = {".json", ".jsonl", ".yaml", ".yml", ".txt", ".md"}
MANAGED_FEED_PATHS = (
    ".gitattributes",
    "feed.yaml",
    "manifests",
    "papers",
    "schemas",
    "checksums",
)
SYNC_JOURNAL_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PublishableRawRecord:
    source_path: Path
    paper_uid: str
    source_version: int
    destination_path: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_feed_inventory(root: Path) -> dict[str, str]:
    """Hash every managed Feed file while ignoring volatile timestamps."""

    if not root.exists():
        return {}
    inventory: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith("checksums/") or ".git" in Path(relative).parts:
            continue
        if Path(relative).parts[0] not in MANAGED_FEED_PATHS:
            continue
        if relative == "manifests/current.json":
            value = json.loads(path.read_text(encoding="utf-8"))
            value.pop("generated_at", None)
            payload = _json_line(value).encode("utf-8")
            inventory[relative] = hashlib.sha256(payload).hexdigest()
        elif relative == "feed.yaml":
            from ruamel.yaml import YAML

            value = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
            value.pop("generated_at", None)
            payload = _json_line(value).encode("utf-8")
            inventory[relative] = hashlib.sha256(payload).hexdigest()
        else:
            inventory[relative] = _sha256(path)
    return inventory


def _json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _copy_if_changed(source: Path, target: Path) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = source.read_bytes()
    if source.suffix.casefold() in FEED_TEXT_SUFFIXES:
        payload = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if target.exists() and target.read_bytes() == payload:
        return False
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(target)
    return True


def _source_records(root: Path) -> tuple[list[Path], list[Path]]:
    raw_root = root / ".paperflow/data/raw"
    raw = sorted(
        path
        for path in raw_root.glob("*/*/v*.json")
        if path.is_file() and re.fullmatch(r"v[1-9][0-9]*\.json", path.name)
    )
    ai = sorted(
        path
        for path in (root / ".paperflow/data/ai").rglob("*.json")
        if "subscriptions" not in path.parts and path.name != "current.json"
    )
    return raw, ai


def _publishable_raw_records(root: Path, sources: list[Path]) -> list[PublishableRawRecord]:
    records: list[PublishableRawRecord] = []
    business_keys: set[tuple[str, int]] = set()
    destinations: set[str] = set()
    parsed = [
        (source, RawPaperRecord.model_validate_json(source.read_text(encoding="utf-8")))
        for source in sources
    ]
    components = assert_distinct_storage_components(
        [record.paper_uid for _, record in parsed], label="paper_uid"
    )
    for source, internal in parsed:
        uid = components[internal.paper_uid]
        destination = Path("papers") / uid / "raw" / f"v{internal.source_version}.json"
        business_key = (internal.paper_uid, internal.source_version)
        destination_key = destination.as_posix()
        if business_key in business_keys:
            raise ValueError(
                f"duplicate canonical Raw business key: {internal.paper_uid} "
                f"v{internal.source_version}"
            )
        if destination_key in destinations:
            raise ValueError(f"duplicate Raw destination path: {destination_key}")
        business_keys.add(business_key)
        destinations.add(destination_key)
        records.append(
            PublishableRawRecord(
                source_path=source,
                paper_uid=internal.paper_uid,
                source_version=internal.source_version,
                destination_path=destination,
            )
        )
    return records


def _inventory(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def _sync_journal_path(destination: Path) -> Path:
    return destination.parent / f".{destination.name}.paperflow-sync.json"


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _copy_path(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target)
    elif source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _replace_managed_path(source: Path, target: Path) -> None:
    _remove_path(target)
    _copy_path(source, target)


def _managed_inventory(root: Path) -> dict[str, str]:
    inventory: dict[str, str] = {}
    for name in MANAGED_FEED_PATHS:
        path = root / name
        if path.is_file():
            inventory[name] = _sha256(path)
        elif path.is_dir():
            inventory.update(
                {
                    child.relative_to(root).as_posix(): _sha256(child)
                    for child in path.rglob("*")
                    if child.is_file()
                }
            )
    return inventory


def _write_sync_journal(
    destination: Path,
    transaction: Path,
    *,
    phase: str,
) -> None:
    atomic_json(
        _sync_journal_path(destination),
        {
            "schema_version": SYNC_JOURNAL_SCHEMA_VERSION,
            "destination_name": destination.name,
            "transaction_dir": transaction.name,
            "managed_paths": list(MANAGED_FEED_PATHS),
            "phase": phase,
        },
    )


def _read_sync_journal(destination: Path) -> tuple[dict[str, Any], Path]:
    journal_path = _sync_journal_path(destination)
    try:
        value = json.loads(journal_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid Feed sync journal: {journal_path}") from exc
    prefix = f".{destination.name}.paperflow-sync-"
    transaction_name = value.get("transaction_dir")
    valid = (
        value.get("schema_version") == SYNC_JOURNAL_SCHEMA_VERSION
        and value.get("destination_name") == destination.name
        and value.get("managed_paths") == list(MANAGED_FEED_PATHS)
        and value.get("phase") in {"prepared", "applying", "committed"}
        and isinstance(transaction_name, str)
        and transaction_name.startswith(prefix)
        and Path(transaction_name).name == transaction_name
    )
    if not valid:
        raise RuntimeError(f"Unsafe Feed sync journal: {journal_path}")
    transaction = destination.parent / transaction_name
    try:
        transaction.resolve().relative_to(destination.parent.resolve())
    except ValueError as exc:
        raise RuntimeError(f"Unsafe Feed sync transaction: {transaction}") from exc
    return value, transaction


def _recover_managed_feed_sync(destination: Path) -> bool:
    """Roll back an interrupted managed-path update before another build."""

    journal_path = _sync_journal_path(destination)
    if not journal_path.exists():
        return False
    value, transaction = _read_sync_journal(destination)
    if value["phase"] != "committed":
        backup = transaction / "backup"
        if not backup.is_dir():
            raise RuntimeError(f"Feed sync backup is missing: {backup}")
        destination.mkdir(parents=True, exist_ok=True)
        for name in MANAGED_FEED_PATHS:
            _replace_managed_path(backup / name, destination / name)
        if _managed_inventory(destination) != _managed_inventory(backup):
            raise RuntimeError("Feed sync rollback verification failed")
    journal_path.unlink()
    shutil.rmtree(transaction, ignore_errors=True)
    return True


def _prepare_managed_feed_sync(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(parents=True, exist_ok=True)
    transaction = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.paperflow-sync-",
            dir=str(destination.parent),
        )
    )
    backup = transaction / "backup"
    backup.mkdir()
    try:
        for name in MANAGED_FEED_PATHS:
            _copy_path(destination / name, backup / name)
        _write_sync_journal(destination, transaction, phase="prepared")
    except BaseException:
        shutil.rmtree(transaction, ignore_errors=True)
        raise
    return transaction


def _sync_managed_feed(staging: Path, destination: Path) -> None:
    """Synchronize PaperFlow-owned paths with crash-recoverable rollback."""

    _recover_managed_feed_sync(destination)
    transaction = _prepare_managed_feed_sync(destination)
    try:
        _write_sync_journal(destination, transaction, phase="applying")
        for name in MANAGED_FEED_PATHS:
            _replace_managed_path(staging / name, destination / name)
        _write_sync_journal(destination, transaction, phase="committed")
        _sync_journal_path(destination).unlink()
        shutil.rmtree(transaction, ignore_errors=True)
    except BaseException:
        _recover_managed_feed_sync(destination)
        raise


def _community_records(root: Path) -> list[Path]:
    return sorted(
        (root / ".paperflow/data/community/outbox").glob("papers/*/community/*/*/r*.json")
    )


def _publish_community(
    root: Path,
    destination: Path,
    *,
    enabled: bool,
) -> tuple[int, int, int]:
    """Publish only explicit, already-sanitized immutable outbox snapshots."""
    if not enabled:
        shutil.rmtree(destination / "manifests/community", ignore_errors=True)
        for path in destination.glob("papers/*/community"):
            shutil.rmtree(path, ignore_errors=True)
        return 0, 0, 0
    from paperflow.community.models import CommunityContribution
    from paperflow.community.privacy import scan_community_contribution

    records = _community_records(root)
    by_paper: dict[str, list[dict[str, Any]]] = {}
    contributors: set[str] = set()
    reviews = 0
    manifest_root = destination / "manifests/community"
    manifest_root.mkdir(parents=True, exist_ok=True)
    for source in records:
        value = CommunityContribution.model_validate_json(source.read_text(encoding="utf-8"))
        findings = scan_community_contribution(value.model_dump(mode="json"))
        if findings:
            raise RuntimeError(f"{source}: {', '.join(findings)}")
        relative = source.relative_to(root / ".paperflow/data/community/outbox")
        target = resolve_under(destination, *relative.parts, label="Community Feed staging path")
        _copy_if_changed(source, target)
        entry = {
            "paper_uid": value.paper_uid,
            "contribution_id": value.contribution_id,
            "creator": value.creator,
            "revision": value.revision,
            "path": relative.as_posix(),
            "sha256": _sha256(target),
        }
        by_paper.setdefault(value.paper_uid, []).append(entry)
        contributors.add(value.creator)
        reviews += int(value.kind == "paper-review")
    for paper_uid, entries in sorted(by_paper.items()):
        path = resolve_under(
            manifest_root,
            f"{encode_storage_component_v2(paper_uid, label='paper_uid')}.jsonl",
            label="Community manifest path",
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(_json_line(item) + "\n" for item in entries),
            encoding="utf-8",
            newline="\n",
        )
    if not by_paper:
        (manifest_root / "all.jsonl").write_text("", encoding="utf-8", newline="\n")
    return len(records), reviews, len(contributors)


def publish_plan(root: Path, settings: WorkspaceSettings) -> dict[str, Any]:
    raw, ai = _source_records(root)
    return {
        "enabled": settings.publishing.enabled,
        "feed_id": settings.publishing.feed_id,
        "raw_records": len(raw) if settings.publishing.include_raw_metadata else 0,
        "ai_records": len(ai) if settings.publishing.include_ai_analysis else 0,
        "include_pdf_files": settings.publishing.include_pdf_files,
        "pdf_policy": settings.publishing.pdf_policy,
        "user_records": 0,
        "rendered_notes": 0,
        "community_contributions": (
            len(_community_records(root))
            if settings.publishing.include_community_contributions
            else 0
        ),
        "requires_data_license": not bool(settings.publishing.data_license),
    }


def _build_feed_tree(
    root: Path,
    settings: WorkspaceSettings,
    destination: Path,
    *,
    previous_feed: Path | None = None,
) -> dict[str, Any]:
    publishing = settings.publishing
    if not publishing.feed_id or not publishing.name:
        raise ValueError("publishing.feed_id and publishing.name are required")
    if not publishing.data_license:
        raise ValueError("publishing.data_license is required before building a public Feed")
    if publishing.include_pdf_files or publishing.pdf_policy != "link-only":
        raise ValueError(
            "PDF redistribution is disabled by default; only link-only feeds "
            "are supported until explicit per-paper licence checks are configured."
        )
    destination.mkdir(parents=True, exist_ok=True)
    (destination / ".gitattributes").write_text(
        "* text=auto eol=lf\n",
        encoding="utf-8",
        newline="\n",
    )
    raw, ai = _source_records(root)
    publishable_raw = _publishable_raw_records(root, raw)
    PublishScanner(root).assert_clean([*raw, *ai, *_community_records(root)])
    community_count, community_review_count, contributor_count = _publish_community(
        root,
        destination,
        enabled=publishing.include_community_contributions,
    )
    paper_manifest: list[dict[str, Any]] = []
    analysis_manifest: list[dict[str, Any]] = []
    changed = 0

    if publishing.include_raw_metadata:
        for item in publishable_raw:
            internal = RawPaperRecord.model_validate_json(
                item.source_path.read_text(encoding="utf-8")
            )
            public = PublicRawPaperRecord.from_internal(internal)
            target = resolve_under(
                destination,
                *item.destination_path.parts,
                label="Raw Feed staging path",
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                public.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            changed += 1
            record = public.model_dump(mode="json")
            metadata = record["metadata"]
            version = public.source_version
            paper_manifest.append(
                {
                    "paper_uid": public.paper_uid,
                    "source": public.source,
                    "source_id": public.source_id,
                    "version": version,
                    "year": metadata.get("paper_year")
                    or str(metadata.get("paper_submitted_date") or "")[:4]
                    or "Unclassified",
                    "path": target.relative_to(destination).as_posix(),
                    "sha256": _sha256(target),
                    "pdf": {
                        "source_url": metadata.get("paper_pdf_url", ""),
                        "arxiv_abs_url": metadata.get("paper_abs_url", ""),
                        "arxiv_version": version,
                        "expected_sha256": public.pdf_sha256,
                        "expected_size": None,
                        "redistribute": False,
                    },
                }
            )
    if publishing.include_ai_analysis:
        ai_values = [json.loads(source.read_text(encoding="utf-8")) for source in ai]
        ai_papers = assert_distinct_storage_components(
            [record["paper_uid"] for record in ai_values], label="paper_uid"
        )
        analysis_ids = assert_distinct_storage_components(
            [record["analysis_id"] for record in ai_values], label="analysis_id"
        )
        for source, record in zip(ai, ai_values, strict=True):
            uid = ai_papers[str(record["paper_uid"])]
            identity = record["identity"]
            provider = safe_storage_component(identity["provider"], label="provider")
            target = resolve_under(
                destination,
                "papers",
                uid,
                "ai",
                provider,
                f"{analysis_ids[str(record['analysis_id'])]}.json",
                label="AI Feed staging path",
            )
            changed += int(_copy_if_changed(source, target))
            analysis_manifest.append(
                {
                    "paper_uid": record["paper_uid"],
                    "analysis_id": record["analysis_id"],
                    "provider": provider,
                    "model": identity.get("model", ""),
                    "profile": identity.get("profile", ""),
                    "path": target.relative_to(destination).as_posix(),
                    "sha256": _sha256(target),
                }
            )

    paper_manifest.sort(key=lambda item: (item["paper_uid"], item["version"]))
    analysis_manifest.sort(key=lambda item: (item["paper_uid"], item["analysis_id"]))
    manifests = destination / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    paper_manifest_text = "".join(_json_line(item) + "\n" for item in paper_manifest)
    analysis_manifest_text = "".join(_json_line(item) + "\n" for item in analysis_manifest)
    paper_manifest_path = manifests / "papers.jsonl"
    analysis_manifest_path = manifests / "analyses.jsonl"
    previous_paper_manifest = (
        previous_feed / "manifests/papers.jsonl" if previous_feed is not None else None
    )
    previous_analysis_manifest = (
        previous_feed / "manifests/analyses.jsonl" if previous_feed is not None else None
    )
    previous_papers = (
        previous_paper_manifest.read_text(encoding="utf-8")
        if previous_paper_manifest is not None and previous_paper_manifest.exists()
        else None
    )
    previous_analyses = (
        previous_analysis_manifest.read_text(encoding="utf-8")
        if previous_analysis_manifest is not None and previous_analysis_manifest.exists()
        else None
    )
    previous_community = (
        _inventory(previous_feed / "manifests/community") if previous_feed is not None else {}
    )
    current_community = _inventory(manifests / "community")
    content_changed = (
        previous_papers != paper_manifest_text
        or previous_analyses != analysis_manifest_text
        or previous_community != current_community
    )
    paper_manifest_path.write_text(
        paper_manifest_text,
        encoding="utf-8",
        newline="\n",
    )
    analysis_manifest_path.write_text(
        analysis_manifest_text,
        encoding="utf-8",
        newline="\n",
    )
    previous_current_path = (
        previous_feed / "manifests/current.json"
        if previous_feed is not None
        else manifests / "missing-current.json"
    )
    previous_current = {}
    if previous_current_path.exists():
        try:
            previous_current = json.loads(previous_current_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous_current = {}
    content_changed = content_changed or (
        int(previous_current.get("community_contribution_count", 0)) != community_count
    )
    generated_at = (
        WorkspaceClock(settings.timezone).iso_now()
        if content_changed or not previous_current.get("generated_at")
        else str(previous_current["generated_at"])
    )
    current = {
        "feed_schema_version": VERSIONS.public_feed_schema_version,
        "generated_at": generated_at,
        "paper_count": len(paper_manifest),
        "analysis_count": len(analysis_manifest),
        "community_contribution_count": community_count,
        "community_review_count": community_review_count,
        "contributor_count": contributor_count,
        "application_version": APPLICATION_VERSION,
    }
    (manifests / "current.json").write_text(
        json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    feed = {
        "feed_schema_version": VERSIONS.public_feed_schema_version,
        "feed_id": publishing.feed_id,
        "name": publishing.name,
        "publisher": {
            "name": publishing.publisher_name,
            "url": publishing.publisher_url,
        },
        "generated_at": generated_at,
        # Raw/AI paths remain readable by 1.4. Community-aware readers inspect
        # capabilities and community_data_schema_version before opting in.
        "minimum_reader_version": "1.4.0",
        "default_branch": publishing.branch,
        "data_license": publishing.data_license,
        "pdf_policy": "link-only",
        "arxiv_attribution": True,
        "community_data_schema_version": VERSIONS.community_data_schema_version,
        "capabilities": {
            "raw": publishing.include_raw_metadata,
            "ai": publishing.include_ai_analysis,
            "community": publishing.include_community_contributions,
        },
        "schemas": {
            "raw": "schemas/public-raw-paper.schema.json",
            "ai": "schemas/ai-analysis.schema.json",
            "community": "schemas/community-contribution.schema.json",
        },
        "licenses": {
            "data": publishing.data_license,
            "community": publishing.data_license,
        },
        "policy": {
            "pdf": "link-only",
            "community_opt_in": publishing.include_community_contributions,
            "maximum_quote_characters": 500,
        },
    }
    dump_yaml(destination / "feed.yaml", feed)
    feed_yaml = destination / "feed.yaml"
    feed_yaml.write_bytes(feed_yaml.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    schema_dir = destination / "schemas"
    schema_dir.mkdir(exist_ok=True)
    for name in [
        "raw-paper.schema.json",
        "public-raw-paper.schema.json",
        "ai-analysis.schema.json",
        "feed.schema.json",
        "community-contribution.schema.json",
        "community-profile.schema.json",
        "community-retraction.schema.json",
        "community-manifest.schema.json",
    ]:
        candidates = [
            root / "schemas" / name,
            root / ".paperflow/schemas" / name,
        ]
        schema_source = next(
            (candidate for candidate in candidates if candidate.is_file()),
            None,
        )
        if schema_source is None:
            from paperflow.workspace import _distribution_resource

            schema_source = _distribution_resource("schemas") / name
        if not schema_source.is_file():
            raise FileNotFoundError(f"Required Feed schema is missing: {name}")
        _copy_if_changed(schema_source, schema_dir / name)
    canonical_changed = _canonical_feed_inventory(destination) != (
        _canonical_feed_inventory(previous_feed) if previous_feed is not None else {}
    )
    if canonical_changed and not content_changed:
        generated_at = WorkspaceClock(settings.timezone).iso_now()
        current["generated_at"] = generated_at
        feed["generated_at"] = generated_at
        (manifests / "current.json").write_text(
            json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        dump_yaml(destination / "feed.yaml", feed)
        feed_yaml.write_bytes(feed_yaml.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    content_changed = canonical_changed
    checksums = []
    for path in sorted(
        item
        for item in destination.rglob("*")
        if item.is_file()
        and "checksums" not in item.parts
        and ".git" not in item.relative_to(destination).parts
    ):
        checksums.append(f"{_sha256(path)}  {path.relative_to(destination).as_posix()}")
    checksum_file = destination / "checksums/sha256.txt"
    checksum_file.parent.mkdir(parents=True, exist_ok=True)
    checksum_file.write_text(
        "\n".join(checksums) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    validation = validate_feed(destination)
    findings = scan_feed(destination)
    if findings:
        raise RuntimeError("Public Feed privacy scan failed:\n" + "\n".join(findings))
    return {
        "destination": str(destination),
        "changed_records": changed,
        "content_changed": content_changed,
        "paper_count": len(paper_manifest),
        "analysis_count": len(analysis_manifest),
        "validation": validation,
        "privacy_scan": "passed",
    }


def build_feed(
    root: Path,
    settings: WorkspaceSettings,
    destination: Path | None = None,
) -> dict[str, Any]:
    """Build and validate a clean candidate before touching the current Feed."""

    final_destination = destination or root / ".paperflow/publish/feed"
    final_destination = final_destination.resolve()
    final_destination.parent.mkdir(parents=True, exist_ok=True)
    _recover_managed_feed_sync(final_destination)
    staging = Path(
        tempfile.mkdtemp(
            prefix=".paperflow-feed-staging-",
            dir=str(final_destination.parent),
        )
    )
    try:
        result = _build_feed_tree(
            root,
            settings,
            staging,
            previous_feed=final_destination if final_destination.exists() else None,
        )
        _sync_managed_feed(staging, final_destination)
        return {**result, "destination": str(final_destination)}
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _manifest_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def resolve_feed_file(feed_root: Path, relative: str) -> Path:
    text = str(relative)
    normalized = text.replace("\\", "/")
    parts = normalized.split("/")
    if ".." in parts:
        raise ValueError(f"Feed path escapes its root: {relative}")
    if (
        not text
        or Path(text).is_absolute()
        or normalized.startswith("/")
        or normalized.startswith("//")
        or re.match(r"(?i)^[a-z]:", normalized)
        or any(part in {"", "."} for part in parts)
    ):
        raise ValueError(f"Feed path must be a safe relative path: {relative}")
    candidate = (feed_root.resolve() / Path(*parts)).resolve()
    try:
        candidate.relative_to(feed_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Feed path escapes its root: {relative}") from exc
    return candidate


def validate_feed(feed_root: Path) -> dict[str, Any]:
    from ruamel.yaml import YAML

    feed = YAML(typ="safe").load((feed_root / "feed.yaml").read_text(encoding="utf-8"))
    Draft202012Validator(
        json.loads((feed_root / "schemas/feed.schema.json").read_text(encoding="utf-8"))
    ).validate(feed)
    found_version = int(feed["feed_schema_version"])
    if found_version not in (1, VERSIONS.public_feed_schema_version):
        raise ValueError("Unsupported Feed schema version")
    check_reader_version(str(feed["minimum_reader_version"]))
    if feed.get("pdf_policy") != "link-only":
        raise ValueError("Feed PDF policy must be link-only")
    checksum_file = feed_root / "checksums/sha256.txt"
    checksum_paths: set[str] = set()
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        if relative in checksum_paths:
            raise ValueError(f"duplicate checksum path: {relative}")
        checksum_paths.add(relative)
        target = resolve_feed_file(feed_root, relative)
        if not target.is_file() or _sha256(target) != expected:
            raise ValueError(f"Checksum mismatch: {relative}")
    actual_paths = {
        path.relative_to(feed_root).as_posix()
        for path in feed_root.rglob("*")
        if path.is_file()
        and not path.relative_to(feed_root).as_posix().startswith("checksums/")
        and ".git" not in path.relative_to(feed_root).parts
    }
    if checksum_paths != actual_paths:
        missing = sorted(actual_paths - checksum_paths)
        extra = sorted(checksum_paths - actual_paths)
        raise ValueError(f"checksum inventory mismatch: unlisted={missing}, missing={extra}")
    schemas = feed.get("schemas", {})
    raw_schema_path = resolve_feed_file(
        feed_root,
        str(schemas.get("raw") or "schemas/raw-paper.schema.json"),
    )
    ai_schema_path = resolve_feed_file(
        feed_root,
        str(schemas.get("ai") or "schemas/ai-analysis.schema.json"),
    )
    raw_validator = Draft202012Validator(json.loads(raw_schema_path.read_text(encoding="utf-8")))
    ai_validator = Draft202012Validator(json.loads(ai_schema_path.read_text(encoding="utf-8")))
    papers = _manifest_lines(feed_root / "manifests/papers.jsonl")
    analyses = _manifest_lines(feed_root / "manifests/analyses.jsonl")
    manifest_paths: set[str] = set()
    raw_keys: set[tuple[str, int]] = set()
    for item in papers:
        relative = str(item["path"])
        raw_key = (str(item["paper_uid"]), int(item["version"]))
        if relative in manifest_paths:
            raise ValueError(f"duplicate manifest path: {relative}")
        if raw_key in raw_keys:
            raise ValueError(f"duplicate Raw business key: {raw_key[0]} v{raw_key[1]}")
        manifest_paths.add(relative)
        raw_keys.add(raw_key)
        target = resolve_feed_file(feed_root, relative)
        if not target.is_file():
            raise ValueError(f"Raw manifest file is missing: {relative}")
        if _sha256(target) != str(item.get("sha256") or ""):
            raise ValueError(f"Raw manifest hash mismatch: {relative}")
        value = json.loads(target.read_text(encoding="utf-8"))
        raw_validator.validate(value)
        if (
            value.get("paper_uid") != item.get("paper_uid")
            or int(value.get("source_version") or 0) != int(item.get("version") or 0)
            or value.get("source") != item.get("source")
            or value.get("source_id") != item.get("source_id")
        ):
            raise ValueError(f"Raw manifest identity mismatch: {relative}")
    ai_keys: set[tuple[str, str]] = set()
    for item in analyses:
        relative = str(item["path"])
        ai_key = (str(item["paper_uid"]), str(item["analysis_id"]))
        if relative in manifest_paths:
            raise ValueError(f"duplicate manifest path: {relative}")
        if ai_key in ai_keys:
            raise ValueError(f"duplicate AI business key: {ai_key[0]} {ai_key[1]}")
        manifest_paths.add(relative)
        ai_keys.add(ai_key)
        target = resolve_feed_file(feed_root, relative)
        if not target.is_file():
            raise ValueError(f"AI manifest file is missing: {relative}")
        if _sha256(target) != str(item.get("sha256") or ""):
            raise ValueError(f"AI manifest hash mismatch: {relative}")
        value = json.loads(target.read_text(encoding="utf-8"))
        ai_validator.validate(value)
        if value.get("paper_uid") != item.get("paper_uid") or value.get("analysis_id") != item.get(
            "analysis_id"
        ):
            raise ValueError(f"AI manifest identity mismatch: {relative}")
        identity = value.get("identity", {})
        for provenance_key in [
            "provider",
            "model",
            "profile",
            "prompt_version",
            "analysis_schema_version",
            "source_content_hash",
        ]:
            if provenance_key not in identity:
                raise ValueError(f"Incomplete AI provenance: missing {provenance_key}")
    community_count = 0
    if found_version >= 2 and feed.get("capabilities", {}).get("community"):
        from paperflow.community.manifest import load_community_manifest
        from paperflow.community.privacy import scan_community_contribution

        load_community_manifest(feed_root)

        community_keys: set[tuple[str, str, int]] = set()
        community_validator = Draft202012Validator(
            json.loads(
                (feed_root / "schemas/community-contribution.schema.json").read_text(
                    encoding="utf-8"
                )
            )
        )
        manifest_validator = Draft202012Validator(
            json.loads(
                (feed_root / "schemas/community-manifest.schema.json").read_text(encoding="utf-8")
            )
        )
        for manifest in sorted((feed_root / "manifests/community").glob("*.jsonl")):
            for item in _manifest_lines(manifest):
                manifest_validator.validate(item)
                relative = str(item["path"])
                community_key = (
                    str(item["paper_uid"]),
                    str(item["contribution_id"]),
                    int(item["revision"]),
                )
                if relative in manifest_paths:
                    raise ValueError(f"duplicate manifest path: {relative}")
                if community_key in community_keys:
                    raise ValueError(
                        "duplicate Community business key: "
                        f"{community_key[0]} {community_key[1]} "
                        f"r{community_key[2]}"
                    )
                manifest_paths.add(relative)
                community_keys.add(community_key)
                target = resolve_feed_file(feed_root, relative)
                if not target.is_file():
                    raise ValueError(f"Community manifest file is missing: {relative}")
                value = json.loads(target.read_text(encoding="utf-8"))
                community_validator.validate(value)
                if _sha256(target) != item["sha256"]:
                    raise ValueError(f"Community manifest hash mismatch: {relative}")
                if (
                    value.get("paper_uid") != item.get("paper_uid")
                    or value.get("contribution_id") != item.get("contribution_id")
                    or int(value.get("revision") or 0) != int(item.get("revision") or 0)
                ):
                    raise ValueError(f"Community manifest identity mismatch: {relative}")
                findings = scan_community_contribution(value)
                if findings:
                    raise ValueError(f"Unsafe Community contribution {item['path']}: {findings}")
                community_count += 1
    return {
        "ok": True,
        "papers": len(papers),
        "analyses": len(analyses),
        "community_contributions": community_count,
        "checksums": "ok",
    }


def scan_feed(feed_root: Path) -> list[str]:
    findings: list[str] = []
    for path in feed_root.rglob("*"):
        if not path.is_file():
            continue
        if ".git" in path.relative_to(feed_root).parts:
            continue
        relative = path.relative_to(feed_root).as_posix()
        if path.name.casefold() in FORBIDDEN_NAMES or path.suffix.casefold() in FORBIDDEN_SUFFIXES:
            findings.append(f"forbidden file: {relative}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "USER_NOTES_START" in text or "USER_NOTES_END" in text:
            findings.append(f"user notes marker: {relative}")
        if re.search(r'(?i)"?user_[A-Za-z0-9_]*"?\s*[:=]', text):
            findings.append(f"user field: {relative}")
        if ABSOLUTE_PATH_RE.search(text):
            findings.append(f"absolute local path: {relative}")
        if SECRET_RE.search(text):
            findings.append(f"possible secret: {relative}")
    return sorted(set(findings))


def feed_diff(feed_root: Path, candidate: Path) -> dict[str, list[str]]:
    def inventory(root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): _sha256(path)
            for path in root.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(root).parts
        }

    old = inventory(feed_root) if feed_root.exists() else {}
    new = inventory(candidate)
    return {
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
        "changed": sorted(name for name in set(old) & set(new) if old[name] != new[name]),
    }


def create_snapshot(
    feed_root: Path,
    destination: Path | None = None,
    *,
    timezone_name: str | None = None,
) -> dict[str, str]:
    validation = validate_feed(feed_root)
    findings = scan_feed(feed_root)
    if findings:
        raise RuntimeError("Cannot snapshot an unsafe Feed: " + repr(findings))
    current_manifest = feed_root / "manifests/current.json"
    current = json.loads(current_manifest.read_text(encoding="utf-8"))
    generated_at = parse_aware_datetime(
        str(current["generated_at"]), field="manifests/current.json generated_at"
    )
    if timezone_name:
        now = WorkspaceClock(timezone_name).now()
    else:
        now = datetime.now(generated_at.tzinfo)
    date = now.strftime("%Y%m%d")
    destination = destination or feed_root.parent / "snapshots"
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"paperflow-feed-v{VERSIONS.public_feed_schema_version}-{date}.tar.zst"
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as temporary:
        tar_path = Path(temporary.name)
    try:
        with tarfile.open(tar_path, "w") as tar:

            def exclude_git(metadata: tarfile.TarInfo) -> tarfile.TarInfo | None:
                return None if ".git" in Path(metadata.name).parts else metadata

            tar.add(
                feed_root,
                arcname="paperflow-feed",
                filter=exclude_git,
            )
        compressor = zstandard.ZstdCompressor(level=10)
        with tar_path.open("rb") as source, archive.open("wb") as target:
            compressor.copy_stream(source, target)
    finally:
        tar_path.unlink(missing_ok=True)
    checksum = _sha256(archive)
    checksums = destination / "checksums.txt"
    checksums.write_text(f"{checksum}  {archive.name}\n", encoding="utf-8")
    metadata = destination / "feed-metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "feed_schema_version": VERSIONS.public_feed_schema_version,
                "created_at": now.isoformat(timespec="seconds"),
                "archive": archive.name,
                "sha256": checksum,
                "validation": validation,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "archive": str(archive),
        "checksums": str(checksums),
        "metadata": str(metadata),
    }
