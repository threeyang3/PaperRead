"""Owner-authenticated, explicitly confirmed submission of selected snapshots."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from paperflow.community.models import CommunityContribution
from paperflow.community.privacy import scan_community_contribution
from paperflow.community.publisher import canonical_content_sha256
from paperflow.feed.git_ops import normalize_github_repository_url
from paperflow.security.paths import safe_storage_component


def submission_plan(root: Path, repository_url: str) -> dict[str, Any]:
    repository = normalize_github_repository_url(repository_url).removeprefix("https://github.com/").removesuffix(".git")
    owner = repository.split("/")[0]
    outbox = root / ".paperflow/data/community/outbox"
    if not outbox.resolve().is_relative_to(root.resolve()):
        raise ValueError("outbox must remain inside the current vault")
    entries = []
    for path in sorted(outbox.rglob("r*.json")):
        if path.is_symlink() or not path.resolve().is_relative_to(outbox.resolve()):
            raise ValueError("outbox snapshot must be a local regular file")
        raw = path.read_bytes()
        if len(raw) > 64 * 1024:
            raise ValueError("snapshot exceeds 64 KiB")
        value = json.loads(raw)
        model = CommunityContribution.model_validate(value)
        if model.creator.casefold() != owner.casefold():
            raise ValueError("owner-only submission requires creator to match repository owner")
        if not hmac.compare_digest(canonical_content_sha256(value), str(value.get("content_sha256") or "")):
            raise ValueError("snapshot content hash mismatch")
        if canonical_content_sha256(model.model_dump(mode="json")) != value["content_sha256"]:
            raise ValueError("snapshot must include normalized schema defaults")
        findings = scan_community_contribution(value)
        if findings:
            raise ValueError("snapshot privacy validation failed: " + ", ".join(findings))
        expected = Path("papers") / safe_storage_component(model.paper_uid, label="paper_uid") / "community" / model.creator / safe_storage_component(model.contribution_id, label="contribution_id") / f"r{model.revision}.json"
        relative = path.relative_to(outbox).as_posix()
        if relative != expected.as_posix():
            raise ValueError("snapshot path does not match its identity")
        entries.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest(),
                        "bytes": len(raw), "paper_uid": model.paper_uid, "kind": model.kind,
                        "creator": model.creator, "revision": model.revision, "license": model.license})
    if len(entries) > 100 or sum(item["bytes"] for item in entries) > 1024 * 1024:
        raise ValueError("submission exceeds 100 snapshots or 1 MiB")
    manifests = sorted({"manifests/community/" + safe_storage_component(item["paper_uid"], label="paper_uid") + ".jsonl" for item in entries})
    payload = {"repository": repository, "access": "owner-only", "files": entries,
               "derived_files": manifests + (["checksums/sha256.txt"] if entries else [])}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {**payload, "plan_sha256": digest, "branch": f"paperflow/community-{digest[:16]}",
            "draft": True, "dry_run": True, "network_changes": 0,
            "ready": bool(entries), "reason": "explicit confirmation required" if entries else "no explicitly selected snapshots"}


class GitHubSubmission:
    def __init__(self, client: httpx.Client):
        self.client = client

    def api(self, method: str, path: str, *, body=None, allow_missing=False):
        response = self.client.request(method, path, json=body)
        if allow_missing and response.status_code == 404:
            return None
        if response.status_code >= 400:
            # Never include a server body or token in exception/log output.
            raise ValueError(f"GitHub {method} request failed (HTTP {response.status_code})")
        return response.json()

    def submit(self, root: Path, plan: dict, confirmation: str) -> dict:
        if not hmac.compare_digest(plan["plan_sha256"], confirmation):
            raise ValueError("confirmation does not match the current publication preview")
        current = submission_plan(root, "https://github.com/" + plan["repository"])
        if current["plan_sha256"] != plan["plan_sha256"] or not current["ready"]:
            raise ValueError("selected snapshots changed or are empty; review a new preview")
        # Freeze all approved bytes before any remote write. A later local edit
        # cannot slip into the approved publication.
        files = []
        outbox = root / ".paperflow/data/community/outbox"
        for item in current["files"]:
            raw = (outbox / item["path"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise ValueError("snapshot changed while preparing submission")
            files.append((item["path"], raw))
        repository = current["repository"]
        owner = repository.split("/")[0]
        actor = self.api("GET", "/user").get("login", "")
        if actor.casefold() != owner.casefold():
            raise ValueError("authenticated GitHub user must be the repository owner")
        prefix = f"/repos/{repository}"
        metadata = self.api("GET", prefix)
        if metadata.get("full_name", "").casefold() != repository.casefold() or metadata.get("archived") or not (metadata.get("permissions") or {}).get("push"):
            raise ValueError("target repository is unavailable or lacks write permission")
        base = metadata["default_branch"]
        base_ref = self.api("GET", prefix + "/git/ref/heads/" + quote(base, safe=""))
        base_sha = base_ref["object"]["sha"]
        changed = []
        for path, raw in files:
            existing = self.api("GET", prefix + "/contents/" + quote(path, safe="/") + "?ref=" + base_sha, allow_missing=True)
            if existing is not None:
                if existing.get("type") != "file" or base64.b64decode(existing.get("content", "")) != raw:
                    raise ValueError("remote immutable revision differs; create a new revision")
            else:
                changed.append((path, raw))
        # Community readers consume only manifested, hash-verified records.
        # Merge selected entries into the pinned upstream indexes and preserve
        # all unrelated entries/checksums; publishing JSON alone is insufficient.
        manifests: dict[str, list[dict]] = {}
        for item in current["files"]:
            manifest_path = "manifests/community/" + safe_storage_component(item["paper_uid"], label="paper_uid") + ".jsonl"
            if manifest_path not in manifests:
                existing = self.api("GET", prefix + "/contents/" + manifest_path + "?ref=" + base_sha, allow_missing=True)
                text = base64.b64decode(existing.get("content", "")).decode("utf-8") if existing else ""
                manifests[manifest_path] = [json.loads(line) for line in text.splitlines() if line.strip()]
            value = json.loads(next(raw for path, raw in files if path == item["path"]))
            entry = {"contribution_id": value["contribution_id"], "creator": item["creator"],
                     "paper_uid": item["paper_uid"], "path": item["path"],
                     "revision": item["revision"], "sha256": item["sha256"]}
            matching = [row for row in manifests[manifest_path] if row.get("path") == item["path"]]
            if matching and (len(matching) != 1 or matching[0] != entry):
                raise ValueError("remote community manifest conflicts with selected revision")
            if not matching:
                manifests[manifest_path].append(entry)
        for path, entries in manifests.items():
            data = ("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for row in sorted(entries, key=lambda row: row["path"])) + "\n").encode()
            existing = self.api("GET", prefix + "/contents/" + path + "?ref=" + base_sha, allow_missing=True)
            if existing is None or base64.b64decode(existing.get("content", "")) != data:
                changed.append((path, data))
        if changed:
            checksum = self.api("GET", prefix + "/contents/checksums/sha256.txt?ref=" + base_sha, allow_missing=True)
            if checksum is None:
                raise ValueError("target must be an initialized PaperFlow Feed with checksums")
            lines = base64.b64decode(checksum.get("content", "")).decode("utf-8").splitlines()
            checksums = {}
            for line in lines:
                if not line.strip(): continue
                digest, path = line.split("  ", 1)
                if path in checksums: raise ValueError("remote checksum index has duplicate paths")
                checksums[path] = digest
            for path, data in changed:
                checksums[path] = hashlib.sha256(data).hexdigest()
            data = ("\n".join(f"{digest}  {path}" for path, digest in sorted(checksums.items())) + "\n").encode()
            changed.append(("checksums/sha256.txt", data))
        if not changed:
            return {"status": "already-published", "network_changes": 0, "plan_sha256": current["plan_sha256"]}
        branch = current["branch"]
        # If a previous submission stopped after pushing, resume only when the
        # branch contains precisely the approved snapshot contents.
        existing_ref = self.api("GET", prefix + "/git/ref/heads/" + quote(branch, safe=""), allow_missing=True)
        if existing_ref:
            ref_sha = existing_ref["object"]["sha"]
            for path, raw in [*files, *[(path, raw) for path, raw in changed if not path.startswith("papers/")]]:
                existing = self.api("GET", prefix + "/contents/" + quote(path, safe="/") + "?ref=" + ref_sha)
                if existing.get("type") != "file" or base64.b64decode(existing.get("content", "")) != raw:
                    raise ValueError("existing submission branch differs; manual review required")
            pulls = self.api("GET", prefix + "/pulls?state=all&head=" + quote(owner + ":" + branch, safe="") + "&base=" + quote(base, safe=""))
            if pulls:
                return {"status": "existing-pr", "url": pulls[0]["html_url"], "plan_sha256": current["plan_sha256"]}
        else:
            commit = self.api("GET", prefix + "/git/commits/" + base_sha)
            blobs = []
            for path, raw in changed:
                blob = self.api("POST", prefix + "/git/blobs", body={"content": base64.b64encode(raw).decode(), "encoding": "base64"})
                blobs.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
            tree = self.api("POST", prefix + "/git/trees", body={"base_tree": commit["tree"]["sha"], "tree": blobs})
            commit = self.api("POST", prefix + "/git/commits", body={"message": "Add selected PaperFlow community snapshots\n\nPlan: " + current["plan_sha256"], "tree": tree["sha"], "parents": [base_sha]})
            self.api("POST", prefix + "/git/refs", body={"ref": "refs/heads/" + branch, "sha": commit["sha"]})
        pull = self.api("POST", prefix + "/pulls", body={"title": "Add selected PaperFlow community snapshots", "head": branch, "base": base, "draft": True,
            "body": f"Publish {len(files)} explicitly selected immutable community snapshots.\n\nPreview SHA-256: {current['plan_sha256']}\n\nPrivacy, identity and content hashes validated locally. No PDFs, original notes or credentials included.\n\n" + "\n".join("- `" + path + "`" for path, _ in files)})
        return {"status": "draft-pr-created", "url": pull["html_url"], "plan_sha256": current["plan_sha256"]}


def submit_confirmed(root: Path, repository_url: str, confirmation: str) -> dict:
    plan = submission_plan(root, repository_url)
    if not hmac.compare_digest(plan["plan_sha256"], confirmation):
        raise ValueError("confirmation does not match the current publication preview")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("GitHub authentication unavailable; provide GH_TOKEN in the process environment")
    with httpx.Client(base_url="https://api.github.com", timeout=30, follow_redirects=False,
                      headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"}) as client:
        return GitHubSubmission(client).submit(root, plan, confirmation)
