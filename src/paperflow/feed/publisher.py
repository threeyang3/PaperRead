from __future__ import annotations

import hashlib
import json
import re
import shutil
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator

from paperflow.versioning import APPLICATION_VERSION, VERSIONS, check_reader_version
from paperflow.workspace import WorkspaceSettings, dump_yaml
import zstandard


BEIJING = ZoneInfo("Asia/Shanghai")
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_line(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


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
    raw = sorted(
        path
        for path in (root / ".paperflow/data/raw").rglob("*.json")
        if "subscriptions" not in path.parts
    )
    ai = sorted(
        path
        for path in (root / ".paperflow/data/ai").rglob("*.json")
        if "subscriptions" not in path.parts
    )
    return raw, ai


def _community_records(root: Path) -> list[Path]:
    return sorted(
        (root / ".paperflow/data/community/outbox").glob(
            "papers/*/community/*/*/r*.json"
        )
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
    for source in records:
        value = CommunityContribution.model_validate_json(
            source.read_text(encoding="utf-8")
        )
        findings = scan_community_contribution(value.model_dump(mode="json"))
        if findings:
            raise RuntimeError(f"{source}: {', '.join(findings)}")
        relative = source.relative_to(
            root / ".paperflow/data/community/outbox"
        )
        target = destination / relative
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
        path = (
            destination
            / "manifests/community"
            / f"{paper_uid.replace(':', '_')}.jsonl"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(_json_line(item) + "\n" for item in entries),
            encoding="utf-8",
            newline="\n",
        )
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


def build_feed(
    root: Path,
    settings: WorkspaceSettings,
    destination: Path | None = None,
) -> dict[str, Any]:
    publishing = settings.publishing
    if not publishing.feed_id or not publishing.name:
        raise ValueError("publishing.feed_id and publishing.name are required")
    if not publishing.data_license:
        raise ValueError(
            "publishing.data_license is required before building a public Feed"
        )
    if publishing.include_pdf_files or publishing.pdf_policy != "link-only":
        raise ValueError(
            "PDF redistribution is disabled by default; only link-only feeds "
            "are supported until explicit per-paper licence checks are configured."
        )
    destination = destination or root / ".paperflow/publish/feed"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / ".gitattributes").write_text(
        "* text=auto eol=lf\n",
        encoding="utf-8",
        newline="\n",
    )
    raw, ai = _source_records(root)
    community_count, community_review_count, contributor_count = (
        _publish_community(
            root,
            destination,
            enabled=publishing.include_community_contributions,
        )
    )
    paper_manifest: list[dict[str, Any]] = []
    analysis_manifest: list[dict[str, Any]] = []
    changed = 0

    if publishing.include_raw_metadata:
        for source in raw:
            record = json.loads(source.read_text(encoding="utf-8"))
            uid = str(record["paper_uid"]).replace(":", "_")
            version = int(record.get("source_version") or 1)
            target = destination / "papers" / uid / "raw" / f"v{version}.json"
            changed += int(_copy_if_changed(source, target))
            metadata = record.get("metadata", {})
            paper_manifest.append(
                {
                    "paper_uid": record["paper_uid"],
                    "source": record["source"],
                    "source_id": record["source_id"],
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
                            "expected_sha256": record.get("pdf_sha256", ""),
                        "expected_size": record.get("extensions", {}).get(
                            "pdf_size"
                        ),
                        "redistribute": False,
                    },
                }
            )
    if publishing.include_ai_analysis:
        for source in ai:
            record = json.loads(source.read_text(encoding="utf-8"))
            uid = str(record["paper_uid"]).replace(":", "_")
            identity = record["identity"]
            provider = identity["provider"]
            target = (
                destination
                / "papers"
                / uid
                / "ai"
                / provider
                / f"{record['analysis_id']}.json"
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
    analysis_manifest.sort(
        key=lambda item: (item["paper_uid"], item["analysis_id"])
    )
    manifests = destination / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    paper_manifest_text = "".join(
        _json_line(item) + "\n" for item in paper_manifest
    )
    analysis_manifest_text = "".join(
        _json_line(item) + "\n" for item in analysis_manifest
    )
    paper_manifest_path = manifests / "papers.jsonl"
    analysis_manifest_path = manifests / "analyses.jsonl"
    previous_papers = (
        paper_manifest_path.read_text(encoding="utf-8")
        if paper_manifest_path.exists()
        else None
    )
    previous_analyses = (
        analysis_manifest_path.read_text(encoding="utf-8")
        if analysis_manifest_path.exists()
        else None
    )
    content_changed = (
        previous_papers != paper_manifest_text
        or previous_analyses != analysis_manifest_text
        or changed > 0
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
    previous_current_path = manifests / "current.json"
    previous_current = {}
    if previous_current_path.exists():
        try:
            previous_current = json.loads(
                previous_current_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            previous_current = {}
    content_changed = content_changed or (
        int(previous_current.get("community_contribution_count", 0))
        != community_count
    )
    generated_at = (
        datetime.now(BEIJING).isoformat()
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
        "community_contribution_count": community_count,
        "community_review_count": community_review_count,
        "contributor_count": contributor_count,
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
            "raw": "schemas/raw-paper.schema.json",
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
    feed_yaml.write_bytes(
        feed_yaml.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    )
    schema_dir = destination / "schemas"
    schema_dir.mkdir(exist_ok=True)
    for name in [
        "raw-paper.schema.json",
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


def _manifest_lines(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def resolve_feed_file(feed_root: Path, relative: str) -> Path:
    candidate = (feed_root.resolve() / Path(relative)).resolve()
    try:
        candidate.relative_to(feed_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Feed path escapes its root: {relative}") from exc
    if Path(relative).is_absolute():
        raise ValueError(f"Feed path must be relative: {relative}")
    return candidate


def validate_feed(feed_root: Path) -> dict[str, Any]:
    from ruamel.yaml import YAML

    feed = YAML(typ="safe").load(
        (feed_root / "feed.yaml").read_text(encoding="utf-8")
    )
    Draft202012Validator(
        json.loads(
            (feed_root / "schemas/feed.schema.json").read_text(
                encoding="utf-8"
            )
        )
    ).validate(feed)
    found_version = int(feed["feed_schema_version"])
    if found_version not in (1, VERSIONS.public_feed_schema_version):
        raise ValueError("Unsupported Feed schema version")
    check_reader_version(str(feed["minimum_reader_version"]))
    if feed.get("pdf_policy") != "link-only":
        raise ValueError("Feed PDF policy must be link-only")
    checksum_file = feed_root / "checksums/sha256.txt"
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        target = resolve_feed_file(feed_root, relative)
        if not target.is_file() or _sha256(target) != expected:
            raise ValueError(f"Checksum mismatch: {relative}")
    raw_schema_path = feed_root / "schemas/raw-paper.schema.json"
    ai_schema_path = feed_root / "schemas/ai-analysis.schema.json"
    raw_validator = Draft202012Validator(
        json.loads(raw_schema_path.read_text(encoding="utf-8"))
    )
    ai_validator = Draft202012Validator(
        json.loads(ai_schema_path.read_text(encoding="utf-8"))
    )
    papers = _manifest_lines(feed_root / "manifests/papers.jsonl")
    analyses = _manifest_lines(feed_root / "manifests/analyses.jsonl")
    for item in papers:
        raw_validator.validate(
            json.loads(
                resolve_feed_file(feed_root, item["path"]).read_text(
                    encoding="utf-8"
                )
            )
        )
    for item in analyses:
        value = json.loads(
            resolve_feed_file(feed_root, item["path"]).read_text(
                encoding="utf-8"
            )
        )
        ai_validator.validate(value)
        identity = value.get("identity", {})
        for key in [
            "provider",
            "model",
            "profile",
            "prompt_version",
            "analysis_schema_version",
            "source_content_hash",
        ]:
            if key not in identity:
                raise ValueError(f"Incomplete AI provenance: missing {key}")
    community_count = 0
    if found_version >= 2 and feed.get("capabilities", {}).get("community"):
        from paperflow.community.privacy import scan_community_contribution

        community_validator = Draft202012Validator(
            json.loads(
                (feed_root / "schemas/community-contribution.schema.json")
                .read_text(encoding="utf-8")
            )
        )
        manifest_validator = Draft202012Validator(
            json.loads(
                (feed_root / "schemas/community-manifest.schema.json")
                .read_text(encoding="utf-8")
            )
        )
        for manifest in sorted((feed_root / "manifests/community").glob("*.jsonl")):
            for item in _manifest_lines(manifest):
                manifest_validator.validate(item)
                value = json.loads(
                    resolve_feed_file(feed_root, item["path"]).read_text(
                        encoding="utf-8"
                    )
                )
                community_validator.validate(value)
                if _sha256(resolve_feed_file(feed_root, item["path"])) != item["sha256"]:
                    raise ValueError(f"Community manifest hash mismatch: {item['path']}")
                findings = scan_community_contribution(value)
                if findings:
                    raise ValueError(
                        f"Unsafe Community contribution {item['path']}: {findings}"
                    )
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
        "changed": sorted(
            name for name in set(old) & set(new) if old[name] != new[name]
        ),
    }


def create_snapshot(
    feed_root: Path, destination: Path | None = None
) -> dict[str, str]:
    validation = validate_feed(feed_root)
    findings = scan_feed(feed_root)
    if findings:
        raise RuntimeError("Cannot snapshot an unsafe Feed: " + repr(findings))
    date = datetime.now(BEIJING).strftime("%Y%m%d")
    destination = destination or feed_root.parent / "snapshots"
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"paperflow-feed-v{VERSIONS.public_feed_schema_version}-{date}.tar.zst"
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as temporary:
        tar_path = Path(temporary.name)
    try:
        with tarfile.open(tar_path, "w") as tar:
            def exclude_git(metadata: tarfile.TarInfo) -> tarfile.TarInfo | None:
                return (
                    None
                    if ".git" in Path(metadata.name).parts
                    else metadata
                )

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
                "created_at": datetime.now(BEIJING).isoformat(),
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
