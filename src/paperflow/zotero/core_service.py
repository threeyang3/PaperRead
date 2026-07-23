"""Loopback-only PaperFlow Core service for the Zotero integration.

The service is intentionally small and dependency-free.  It exposes only
explicit PaperFlow operations, requires a per-process bearer token for every
operation except ``/health``, and never accepts an arbitrary command or path.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import queue
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from paperflow._version import __version__
from paperflow.paths.templates import safe_component
from paperflow.utils import atomic_json, iso_beijing
from paperflow.utils import atomic_write
from paperflow.zotero.store import data_root, runtime_root, state_root
from paperflow.zotero.events import ZoteroEventProcessor
from paperflow.security.artifacts import PermissionGuard


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 23140
SESSION_FILE = "zotero-core-session.json"
PAIRING_TOKEN_FILE = "zotero-core-session.token"
MAX_REQUEST_BYTES = 1024 * 1024


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _paper_path(root: Path, paper_uid: str) -> Path:
    if not paper_uid or len(paper_uid) > 200 or any(char in paper_uid for char in "\\/\x00"):
        raise ValueError("invalid paper_uid")
    directory = data_root(root) / "papers"
    canonical = directory / f"{safe_component(paper_uid)}.json"
    legacy = directory / f"{safe_component(paper_uid.replace(':', '_'))}.json"
    return legacy if legacy.is_file() and not canonical.is_file() else canonical


def _annotation_root(root: Path) -> Path:
    return data_root(root) / "annotations" / "zotero"


def _annotation_component(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 200 or any(char in text for char in "\\/\x00"):
        raise ValueError(f"invalid Zotero {label}")
    return safe_component(text)


def _append_event(root: Path, name: str, payload: dict[str, Any]) -> None:
    target = runtime_root(root) / f"zotero-{name}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {"at": iso_beijing(), "event": name, **payload}
    with target.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


class _Handler(BaseHTTPRequestHandler):
    server_version = "PaperFlowCore/1"

    @property
    def core(self) -> "PaperFlowCoreService":
        return self.server.core  # type: ignore[attr-defined]

    def log_message(self, _format: str, *_args: object) -> None:
        # Do not write request paths, tokens or paper identifiers to stdout.
        return

    def _send(self, status: int, value: object) -> None:
        body = _json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _auth(self) -> bool:
        value = self.headers.get("Authorization", "")
        token = value.removeprefix("Bearer ").strip()
        return bool(token) and hmac.compare_digest(token, self.core.token)

    def _body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("request body too large")
        raw = self.rfile.read(length)
        value = json.loads(raw.decode("utf-8")) if raw else {}
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/health":
            self._send(200, self.core.health())
            return
        if not self._auth():
            self._send(401, {"ok": False, "error": "authentication required"})
            return
        try:
            if path.startswith("/papers/"):
                paper_uid = unquote(path.removeprefix("/papers/"))
                self._send(200, self.core.paper(paper_uid))
                return
            if path.startswith("/zotero/items/") and path.endswith("/status"):
                item_key = unquote(path.removeprefix("/zotero/items/").removesuffix("/status"))
                self._send(200, self.core.item_status(item_key))
                return
            if path.startswith("/zotero/annotations/"):
                paper_uid = unquote(path.removeprefix("/zotero/annotations/"))
                self._send(200, self.core.annotation_list(paper_uid))
                return
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"ok": False, "error": str(exc)})
            return
        self._send(404, {"ok": False, "error": "endpoint not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._auth():
            self._send(401, {"ok": False, "error": "authentication required"})
            return
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            body = self._body()
            if path == "/zotero/events":
                self._send(202, self.core.accept_event(body))
                return
            if path == "/zotero/annotations":
                self._send(202, self.core.mirror_annotation(body))
                return
            if path == "/zotero/migration/results":
                self._send(200, self.core.migration_results(body))
                return
            if path == "/analysis/jobs":
                self._send(202, self.core.enqueue_job("analysis", body))
                return
            if path == "/render/jobs":
                self._send(202, self.core.enqueue_job("render", body))
                return
            if path == "/subscriptions/sync":
                self._send(202, self.core.subscription_sync(body))
                return
            if path == "/community/publish-plan":
                self._send(200, self.core.community_plan(body))
                return
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"ok": False, "error": str(exc)})
            return
        self._send(404, {"ok": False, "error": "endpoint not found"})


class PaperFlowCoreService:
    """A managed loopback service with an append-only session state file."""

    def __init__(self, root: Path, *, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, token: str | None = None):
        if host not in {DEFAULT_HOST, "localhost", "::1"}:
            raise ValueError("PaperFlow Core service must bind to loopback")
        self.root = root.resolve()
        self.host = host
        self.requested_port = port
        self.token = token or secrets.token_urlsafe(32)
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.worker: threading.Thread | None = None
        self.worker_stop = threading.Event()
        self.jobs: queue.Queue[dict[str, Any]] = queue.Queue()

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1]) if self.httpd else self.requested_port

    @property
    def url(self) -> str:
        host = "[::1]" if self.host == "::1" else self.host
        return f"http://{host}:{self.port}"

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "service": "paperflow-core",
            "version": __version__,
            "base_url": self.url,
            "auth": "bearer-token-required-except-health",
            "network_scope": "loopback-only",
        }

    def _write_session(self) -> Path:
        path = state_root(self.root) / SESSION_FILE
        atomic_json(
            path,
            {
                "schema_version": 1,
                "pid": os.getpid(),
                "host": self.host,
                "port": self.port,
                "base_url": self.url,
                "token_sha256": hashlib.sha256(self.token.encode("utf-8")).hexdigest(),
                "started_at": iso_beijing(),
                "network_scope": "loopback-only",
            },
        )
        return path

    def _write_pairing_token(self) -> Path:
        """Write the raw token only to ignored runtime state for local pairing.

        The regular session state stores only a hash.  The token file is
        deliberately under ``.paperflow/runtime`` and is never read by Core
        over HTTP; the user must explicitly request it with the local CLI and
        paste it into the Zotero plugin.
        """
        path = runtime_root(self.root) / PAIRING_TOKEN_FILE
        atomic_write(path, self.token + "\n")
        return path

    def _remove_pairing_token(self) -> None:
        runtime_root(self.root).joinpath(PAIRING_TOKEN_FILE).unlink(missing_ok=True)

    def _start_worker(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.worker_stop.clear()
        self.worker = threading.Thread(
            target=self._worker_loop,
            name="paperflow-core-jobs",
            daemon=True,
        )
        self.worker.start()

    def _worker_loop(self) -> None:
        while not self.worker_stop.is_set():
            try:
                job = self.jobs.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._run_job(job)
            finally:
                self.jobs.task_done()

    def _run_job(self, job: dict[str, Any]) -> None:
        job_id = str(job.get("job_id") or "")
        kind = str(job.get("kind") or "")
        paper_uid = str(job.get("paper_uid") or "")
        _append_event(self.root, "jobs", {"job_id": job_id, "kind": kind, "paper_uid": paper_uid, "status": "running"})
        result: dict[str, Any] = {"job_id": job_id, "kind": kind, "paper_uid": paper_uid}
        try:
            # A standalone Core Data Root deliberately has no Vault pipeline.
            # It remains a safe queue/reader until a configured Workspace is
            # explicitly used as the service root.
            workspace = self.root / ".paperflow/workspace.yaml"
            if not workspace.is_file():
                result.update({"status": "skipped", "reason": "workspace-not-configured"})
            elif kind == "subscription-sync":
                from paperflow.config import load_config
                from paperflow.feed.subscriber import sync_feed
                from paperflow.locking import FileLock
                from paperflow.workspace import load_workspace_settings

                config = load_config(self.root)
                _, settings = load_workspace_settings(self.root)
                requested = {str(value).strip() for value in (job.get("source_names") or []) if str(value).strip()}
                sources = [source for source in settings.subscriptions.sources if source.enabled and (not requested or source.name in requested)]
                results = []
                with FileLock(self.root / ".paperflow/runtime/pipeline.lock"):
                    for source in sources:
                        results.append(sync_feed(
                            self.root,
                            url=source.url,
                            name=source.name,
                            branch=source.branch,
                            trust=source.trust,
                            dry_run=False,
                            auto_download_pdf=source.auto_download_pdf,
                            auto_render_notes=source.auto_render_notes,
                            capabilities=list(source.capabilities),
                        ))
                result.update({"status": "completed", "sources": results, "source_count": len(sources)})
            elif kind in {"analysis", "render"}:
                from paperflow.config import ensure_layout, load_config
                from paperflow.locking import FileLock
                from paperflow.pipeline.analyze import analyze_uid
                from paperflow.pipeline.render import render_uid

                config = load_config(self.root)
                ensure_layout(config)
                with FileLock(self.root / ".paperflow/runtime/pipeline.lock"):
                    value = analyze_uid(config, paper_uid, provider=job.get("provider")) if kind == "analysis" else render_uid(config, paper_uid)
                    if job.get("target") in {"zotero", "obsidian", "both"}:
                        from paperflow.zotero.markdown import render_ai_projection
                        value = {
                            "pipeline": str(value),
                            "ai_projection": render_ai_projection(
                                self.root,
                                paper_uid,
                                zotero_item_key=str(job.get("zotero_item_key") or ""),
                                target=str(job["target"]),
                                apply_changes=True,
                            ),
                        }
                result.update({"status": "completed", "result": str(value)})
            else:
                result.update({"status": "skipped", "reason": "worker-not-implemented"})
        except Exception as exc:  # worker failures remain observable and do not kill Core
            result.update({"status": "failed", "error": str(exc)})
        _append_event(self.root, "jobs", result)

    def start(self, *, background: bool = True) -> dict[str, Any]:
        if self.httpd is not None:
            return {**self.health(), "started": False, "status": "already-running"}
        self.httpd = ThreadingHTTPServer((self.host, self.requested_port), _Handler)
        self.httpd.core = self  # type: ignore[attr-defined]
        session = self._write_session()
        self._write_pairing_token()
        if background:
            self.thread = threading.Thread(target=self.httpd.serve_forever, name="paperflow-core", daemon=True)
            self.thread.start()
        self._start_worker()
        return {**self.health(), "started": True, "session_state": session.relative_to(self.root).as_posix()}

    def serve_forever(self) -> None:
        if self.httpd is None:
            self.httpd = ThreadingHTTPServer((self.host, self.requested_port), _Handler)
            self.httpd.core = self  # type: ignore[attr-defined]
            self._write_session()
            self._write_pairing_token()
            self._start_worker()
        try:
            self.httpd.serve_forever()
        finally:
            # `shutdown()` must be called from another thread.  Foreground
            # shutdown therefore closes the socket directly and removes only
            # this process's session marker.
            self.httpd.server_close()
            self.httpd = None
            self._remove_pairing_token()
            session = state_root(self.root) / SESSION_FILE
            if session.exists():
                try:
                    value = json.loads(session.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    value = {}
                if value.get("pid") == os.getpid():
                    session.unlink(missing_ok=True)

    def stop(self) -> None:
        if self.httpd is None:
            return
        self.worker_stop.set()
        if self.worker and self.worker is not threading.current_thread():
            self.worker.join(timeout=1)
        self.worker = None
        self.httpd.shutdown()
        self.httpd.server_close()
        self.httpd = None
        self._remove_pairing_token()
        session = state_root(self.root) / SESSION_FILE
        if session.exists():
            try:
                value = json.loads(session.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                value = {}
            if value.get("pid") == os.getpid():
                session.unlink(missing_ok=True)

    def paper(self, paper_uid: str) -> dict[str, Any]:
        path = _paper_path(self.root, paper_uid)
        if not path.is_file():
            return {"ok": False, "paper_uid": paper_uid, "status": "not-found"}
        value = json.loads(path.read_text(encoding="utf-8"))
        return {"ok": True, "paper_uid": paper_uid, "paper": value}

    def item_status(self, item_key: str) -> dict[str, Any]:
        if not item_key or len(item_key) > 80 or not item_key.replace("-", "").isalnum():
            raise ValueError("invalid Zotero item key")
        directory = data_root(self.root) / "connectors/zotero/mappings"
        for path in sorted(directory.glob("*.json")) if directory.exists() else []:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if value.get("zotero", {}).get("item_key") == item_key:
                return {"ok": True, "item_key": item_key, "linked": True, "mapping": value}
        return {"ok": True, "item_key": item_key, "linked": False, "status": "unlinked"}

    def annotation_list(self, paper_uid: str) -> dict[str, Any]:
        _annotation_component(paper_uid, "paper UID")
        directory = _annotation_root(self.root) / safe_component(paper_uid)
        annotations: list[dict[str, Any]] = []
        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict):
                    annotations.append(value)
        return {
            "ok": True,
            "paper_uid": paper_uid,
            "count": len(annotations),
            "active_count": sum(1 for item in annotations if not item.get("deleted")),
            "annotations": annotations,
            "permission": "SYSTEM_MANAGED",
        }

    def migration_results(self, body: dict[str, Any]) -> dict[str, Any]:
        """Persist only plugin-returned identity/attachment facts.

        The Core accepts object-API output, never opens Zotero's database and
        never performs an attachment copy.  The plugin remains the only
        Zotero writer.
        """
        from paperflow.zotero.migration import ingest_plugin_results

        result = ingest_plugin_results(self.root, body)
        return {"ok": True, **result}

    def mirror_annotation(self, body: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "event", "paper_uid", "annotation_id", "item_key", "parent_item_key",
            "annotation_type", "text", "comment", "color", "page", "position",
            "tags", "created_at", "updated_at", "deleted",
        }
        unknown = sorted(set(body) - allowed)
        if unknown:
            raise ValueError(f"unsupported annotation fields: {', '.join(unknown)}")
        annotation_id = _annotation_component(body.get("annotation_id") or body.get("item_key"), "annotation id")
        event = str(body.get("event") or "modify").strip().casefold()
        if event == "delete" or body.get("deleted") is True:
            target_paths = []
            if body.get("paper_uid"):
                target_paths = [_annotation_root(self.root) / _annotation_component(body["paper_uid"], "paper UID") / f"{annotation_id}.json"]
            else:
                target_paths = list(_annotation_root(self.root).glob(f"*/{annotation_id}.json"))
            updated = 0
            for target in target_paths:
                if not target.is_file():
                    continue
                try:
                    value = json.loads(target.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(value, dict):
                    continue
                value.update({"deleted": True, "updated_at": body.get("updated_at") or iso_beijing(), "artifact_permission": "SYSTEM_MANAGED"})
                PermissionGuard(self.root).authorize(target, "SYSTEM_MANAGED")
                atomic_json(target, value)
                updated += 1
            return {"ok": True, "status": "deleted", "annotation_id": annotation_id, "updated": updated, "permission": "SYSTEM_MANAGED"}
        paper_uid = str(body.get("paper_uid") or "").strip()
        _annotation_component(paper_uid, "paper UID")
        target = _annotation_root(self.root) / _annotation_component(paper_uid, "paper UID") / f"{annotation_id}.json"
        PermissionGuard(self.root).authorize(target, "SYSTEM_MANAGED")
        text = str(body.get("text") or "")
        comment = str(body.get("comment") or "")
        if len(text) > 100_000 or len(comment) > 100_000:
            raise ValueError("annotation text is too large")
        tags = body.get("tags") or []
        if not isinstance(tags, list) or any(len(str(tag)) > 200 for tag in tags):
            raise ValueError("annotation tags must be a list of short strings")
        value = {
            "schema_version": 1,
            "artifact_permission": "SYSTEM_MANAGED",
            "source": "zotero",
            "paper_uid": paper_uid,
            "annotation_id": annotation_id,
            "item_key": str(body.get("item_key") or annotation_id),
            "parent_item_key": str(body.get("parent_item_key") or ""),
            "annotation_type": str(body.get("annotation_type") or ""),
            "text": text,
            "comment": comment,
            "color": str(body.get("color") or ""),
            "page": body.get("page"),
            "position": body.get("position") if isinstance(body.get("position"), (dict, str, list)) else {},
            "tags": [str(tag) for tag in tags],
            "created_at": str(body.get("created_at") or iso_beijing()),
            "updated_at": str(body.get("updated_at") or iso_beijing()),
            "deleted": False,
        }
        atomic_json(target, value)
        return {"ok": True, "status": "mirrored", "annotation_id": annotation_id, "paper_uid": paper_uid, "path": target.relative_to(self.root).as_posix(), "permission": "SYSTEM_MANAGED"}

    def accept_event(self, body: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "item_key", "event", "item_type", "attachment_keys", "timestamp",
            "is_regular", "in_collection", "has_pdf", "pdf_stable",
            "identity_resolved", "pdf_sha256", "analysis_profile", "paper_uid",
        }
        unknown = sorted(set(body) - allowed)
        if unknown:
            raise ValueError(f"unsupported event fields: {', '.join(unknown)}")
        if not body.get("event") or not body.get("item_key"):
            raise ValueError("item_key and event are required")
        processor_kwargs: dict[str, Any] = {}
        try:
            from paperflow.workspace import load_workspace_settings

            _, settings = load_workspace_settings(self.root)
            trigger = settings.zotero.analysis_trigger
            processor_kwargs = {
                "collection_only": trigger.mode in {"collection_only", "tag_only"},
                "collections": trigger.collections,
                "auto_queue": trigger.mode not in {"manual", "ask"},
            }
        except (OSError, ValueError, KeyError):
            # A standalone Core root has no Workspace policy; retain the
            # conservative collection-only default.
            pass
        pipeline = ZoteroEventProcessor(self.root, **processor_kwargs).handle(body)
        _append_event(self.root, "events", {key: body[key] for key in body if key in allowed})
        queued_job = None
        if pipeline.get("queue_analysis") and body.get("paper_uid"):
            queued_job = self.enqueue_job(
                "analysis",
                {
                    "paper_uid": body["paper_uid"],
                    "provider": body.get("analysis_profile") or None,
                    "zotero_item_key": body.get("item_key"),
                    "trigger": "zotero-event",
                },
            )
        return {"ok": True, "accepted": True, "status": "observed", "pipeline": pipeline, "job": queued_job}

    def enqueue_job(self, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        paper_uid = str(body.get("paper_uid") or "").strip()
        if not paper_uid:
            raise ValueError("paper_uid is required")
        _paper_path(self.root, paper_uid)
        job_id = f"zotero-{kind}-{secrets.token_hex(8)}"
        allowed = {"paper_uid", "provider", "zotero_item_key", "trigger", "target"}
        unknown = sorted(set(body) - allowed)
        if unknown:
            raise ValueError(f"unsupported job fields: {', '.join(unknown)}")
        target = str(body.get("target") or "").strip().lower()
        if target and target not in {"zotero", "obsidian", "both"}:
            raise ValueError("target must be zotero, obsidian, or both")
        job = {
            "job_id": job_id,
            "kind": kind,
            "paper_uid": paper_uid,
            "provider": body.get("provider"),
            "zotero_item_key": body.get("zotero_item_key"),
            "target": target,
        }
        _append_event(self.root, "jobs", {**job, "status": "queued", "trigger": body.get("trigger", "")})
        self.jobs.put(job)
        return {"ok": True, "job_id": job_id, "status": "queued"}

    def community_plan(self, body: dict[str, Any]) -> dict[str, Any]:
        if not body.get("paper_uid"):
            raise ValueError("paper_uid is required")
        return {
            "ok": True,
            "paper_uid": str(body["paper_uid"]),
            "status": "preview-only",
            "requires_user_confirmation": True,
            "network_changes": 0,
        }

    def subscription_sync(self, body: dict[str, Any]) -> dict[str, Any]:
        allowed = {"source", "source_names", "trigger"}
        unknown = sorted(set(body) - allowed)
        if unknown:
            raise ValueError(f"unsupported subscription fields: {', '.join(unknown)}")
        job_id = f"zotero-subscription-sync-{secrets.token_hex(8)}"
        requested_names = body.get("source_names") or []
        if isinstance(requested_names, str):
            requested_names = [requested_names]
        if not isinstance(requested_names, list):
            raise ValueError("source_names must be a list of source names")
        source_names = [str(value).strip() for value in requested_names if str(value).strip()]
        source = str(body.get("source") or "").strip()
        if source and source not in source_names:
            source_names.append(source)
        job = {
            "job_id": job_id,
            "kind": "subscription-sync",
            "source_names": source_names,
        }
        _append_event(self.root, "jobs", {
            "job_id": job_id,
            "kind": "subscription-sync",
            "status": "queued",
            "source": body.get("source", ""),
            "source_names": source_names,
            "trigger": body.get("trigger", ""),
        })
        self.jobs.put(job)
        return {
            "ok": True,
            "job_id": job_id,
            "status": "queued",
            "requires_confirmation": False,
            "note": "订阅同步将在 Core worker 中读取已配置的只读数据源；不会写 Zotero 数据库。",
        }


def read_session(root: Path) -> dict[str, Any] | None:
    path = state_root(root) / SESSION_FILE
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def read_pairing_token(root: Path) -> str | None:
    path = runtime_root(root) / PAIRING_TOKEN_FILE
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


__all__ = [
    "PaperFlowCoreService",
    "read_session",
    "read_pairing_token",
    "SESSION_FILE",
    "PAIRING_TOKEN_FILE",
]
