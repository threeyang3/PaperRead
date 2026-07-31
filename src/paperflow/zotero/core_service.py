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
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from paperflow._version import __version__
from paperflow.paths.templates import safe_component
from paperflow.utils import atomic_json, iso_utc, sha256_file
from paperflow.utils import atomic_write
from paperflow.zotero.store import data_root, runtime_root, state_root, standalone
from paperflow.zotero.mapping_index import mapping_for_item
from paperflow.zotero.events import ZoteroEventProcessor
from paperflow.security.artifacts import PermissionGuard
from paperflow.security.paths import resolve_under, safe_storage_component


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 23140
SESSION_FILE = "zotero-core-session.json"
PAIRING_TOKEN_FILE = "zotero-core-session.token"
PAIRINGS_FILE = "zotero-pairings.json"
MAX_REQUEST_BYTES = 1024 * 1024
MAX_PDF_CHUNK_BYTES = 768 * 1024
MAX_PDF_BYTES = 100 * 1024 * 1024
JOB_SCHEMA_VERSION = 1
JOB_ID_MAX_LENGTH = 160
JOB_TERMINAL_STATES = frozenset(
    {"cancelled", "completed", "completed-after-cancel-request", "failed", "interrupted", "skipped"}
)
JOB_TRANSITIONS = {
    "queued": {"running", "cancelled"},
    "running": {
        "cancellation-requested",
        "cancelled",
        "completed",
        "completed-after-cancel-request",
        "failed",
        "interrupted",
        "skipped",
    },
    "cancellation-requested": {
        "cancelled",
        "completed-after-cancel-request",
        "failed",
        "interrupted",
    },
}


class JobCancelled(RuntimeError):
    """Cooperative cancellation reached a boundary before a side effect."""


class JobCompletedAfterCancel(RuntimeError):
    """Cancellation arrived after an operation may have produced side effects."""


@dataclass(frozen=True)
class CancellationToken:
    event: threading.Event

    def is_cancelled(self) -> bool:
        return self.event.is_set()

    def raise_if_cancelled(self, *, side_effects: bool = False) -> None:
        if not self.is_cancelled():
            return
        if side_effects:
            raise JobCompletedAfterCancel("cancel requested after operation completed")
        raise JobCancelled("cancel requested")


@dataclass(frozen=True)
class StopResult:
    status: str
    active_job: str | None = None
    process_exit_required: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "active_job": self.active_job,
            "process_exit_required": self.process_exit_required,
        }


@dataclass(frozen=True)
class ServedPdf:
    """Validated PDF metadata; the HTTP layer owns chunked file transfer."""

    path: Path
    filename: str
    sha256: str
    size: int


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _paper_path(root: Path, paper_uid: str) -> Path:
    if not paper_uid or len(paper_uid) > 200 or "\x00" in paper_uid:
        raise ValueError("invalid paper_uid")
    directory = data_root(root) / "papers"
    canonical = directory / f"{safe_component(paper_uid)}.json"
    legacy = directory / f"{safe_component(paper_uid.replace(':', '_'))}.json"
    return legacy if legacy.is_file() and not canonical.is_file() else canonical


def _paper_component(value: object, label: str = "paper UID") -> str:
    text = str(value or "").strip()
    if not text or len(text) > 200 or "\x00" in text:
        raise ValueError(f"invalid {label}")
    return safe_component(text.replace(":", "_"))


def _canonical_paper_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize public Zotero object data into the standalone paper record.

    The plugin is the only component allowed to inspect Zotero objects.  Core
    receives a deliberately small, JSON-only snapshot and stores only the
    canonical PaperMetadata-compatible fields needed by the AI pipeline.
    """
    if not isinstance(snapshot, dict):
        raise ValueError("paper snapshot must be an object")
    paper_uid = str(snapshot.get("paper_uid") or "").strip()
    title = str(snapshot.get("paper_title") or "").strip()
    if not paper_uid or not title:
        raise ValueError("paper_uid and paper_title are required")
    authors = snapshot.get("paper_authors") or []
    if isinstance(authors, str):
        authors = [authors]
    if not isinstance(authors, list) or any(len(str(value)) > 500 for value in authors):
        raise ValueError("paper_authors must be a list of short strings")
    allowed = (
        "paper_uid", "paper_source", "paper_arxiv_id", "paper_arxiv_version",
        "paper_doi", "paper_title", "paper_title_display", "paper_authors",
        "paper_first_author", "paper_year", "paper_submitted_date",
        "paper_updated_date", "paper_published_venue", "paper_primary_category",
        "paper_categories", "paper_abstract", "paper_pdf_url", "paper_abs_url",
        "paper_project_url", "paper_code_url", "paper_dataset_url",
    )
    unknown = sorted(set(snapshot) - set(allowed))
    if unknown:
        raise ValueError(f"unsupported paper snapshot fields: {', '.join(unknown)}")
    value = {key: snapshot[key] for key in allowed if key in snapshot}
    value["paper_uid"] = paper_uid
    value["paper_title"] = title
    value["paper_authors"] = [str(item).strip() for item in authors if str(item).strip()]
    value.setdefault("paper_source", "zotero")
    value.setdefault("paper_arxiv_version", 1)
    value.setdefault("paper_abstract", "")
    value["artifact_permission"] = "RAW_VERSIONED"
    return value


def _annotation_root(root: Path) -> Path:
    return data_root(root) / "annotations" / "zotero"


def _annotation_component(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 200 or "\x00" in text:
        raise ValueError(f"invalid Zotero {label}")
    return safe_component(text)


def _append_event(root: Path, name: str, payload: dict[str, Any]) -> None:
    target = runtime_root(root) / f"zotero-{name}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {"at": iso_utc(), "event": name, **payload}
    with target.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _job_root(root: Path) -> Path:
    """Return the system-managed durable job state directory.

    Jobs are state, not runtime output: keeping them under the Core state root
    means a service restart can recover queued work while the ignored runtime
    directory remains suitable for short-lived logs and pairing tokens.
    """

    return state_root(root) / "jobs"


def _job_path(root: Path, job_id: str) -> Path:
    value = str(job_id or "").strip()
    if (
        not value
        or len(value) > JOB_ID_MAX_LENGTH
        or any(char in value for char in "\\/\x00")
        or not all(char.isalnum() or char in "-_." for char in value)
    ):
        raise ValueError("invalid job_id")
    return _job_root(root) / f"{safe_component(value)}.json"


def _write_job_state(root: Path, value: dict[str, Any]) -> Path:
    target = _job_path(root, str(value.get("job_id") or ""))
    PermissionGuard(root).authorize(target, "SYSTEM_MANAGED")
    atomic_json(target, value)
    return target


def _read_job_state(root: Path, job_id: str) -> dict[str, Any]:
    target = _job_path(root, job_id)
    if not target.is_file():
        raise FileNotFoundError(f"job not found: {job_id}")
    value = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("job_id") != job_id:
        raise ValueError("invalid persisted job state")
    return value


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

    def _send_pdf(self, pdf: ServedPdf) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(pdf.size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-PaperFlow-Sha256", pdf.sha256)
        self.send_header("X-PaperFlow-Filename", pdf.filename)
        self.send_header("Content-Disposition", f'attachment; filename="{pdf.filename}"')
        self.end_headers()
        try:
            with pdf.path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            # A disconnected loopback client must not retain an open handle.
            return

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

    def _raw_body(self, limit: int = MAX_PDF_CHUNK_BYTES) -> bytes:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > limit:
            raise ValueError("request body too large")
        return self.rfile.read(length)

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
            if path.startswith("/zotero/pdf/"):
                paper_uid = unquote(path.removeprefix("/zotero/pdf/"))
                self._send_pdf(self.core.paper_pdf(paper_uid))
                return
            if path.startswith("/zotero/markdown/"):
                paper_uid = unquote(path.removeprefix("/zotero/markdown/"))
                item_key = parse_qs(parsed.query).get("item_key", [""])[0]
                self._send(200, self.core.ai_markdown(paper_uid, item_key=item_key))
                return
            if path.startswith("/zotero/items/") and path.endswith("/status"):
                item_key = unquote(path.removeprefix("/zotero/items/").removesuffix("/status"))
                self._send(200, self.core.item_status(item_key))
                return
            if path.startswith("/zotero/items/") and path.endswith("/workspace"):
                item_key = unquote(path.removeprefix("/zotero/items/").removesuffix("/workspace"))
                self._send(200, self.core.item_workspace(item_key))
                return
            if path.startswith("/zotero/annotations/"):
                paper_uid = unquote(path.removeprefix("/zotero/annotations/"))
                self._send(200, self.core.annotation_list(paper_uid))
                return
            if path.startswith("/community/papers/"):
                paper_uid = unquote(path.removeprefix("/community/papers/"))
                self._send(200, self.core.community_paper(paper_uid))
                return
            if path == "/subscriptions/status":
                self._send(200, self.core.subscription_status())
                return
            if path == "/subscriptions/inbox":
                raw_limit = parse_qs(parsed.query).get("limit", ["100"])[0]
                try:
                    limit = max(1, min(500, int(raw_limit)))
                except ValueError as exc:
                    raise ValueError("limit must be an integer") from exc
                status = parse_qs(parsed.query).get("status", [""])[0]
                self._send(200, self.core.subscription_inbox(limit=limit, status=status))
                return
            if path.startswith("/subscriptions/inbox/"):
                paper_uid = unquote(path.removeprefix("/subscriptions/inbox/"))
                self._send(200, self.core.subscription_inbox_item(paper_uid))
                return
            if path == "/jobs":
                raw_limit = parse_qs(parsed.query).get("limit", ["50"])[0]
                try:
                    limit = max(1, min(200, int(raw_limit)))
                except ValueError as exc:
                    raise ValueError("limit must be an integer") from exc
                self._send(200, self.core.list_jobs(limit=limit))
                return
            if path.startswith("/jobs/"):
                job_id = unquote(path.removeprefix("/jobs/"))
                try:
                    self._send(200, self.core.job(job_id))
                except FileNotFoundError:
                    self._send(404, {"ok": False, "error": "job not found"})
                return
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"ok": False, "error": str(exc)})
            return
        self._send(404, {"ok": False, "error": "endpoint not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/zotero/session/refresh":
            try:
                self._send(200, self.core.refresh_session(self._body()))
            except (OSError, ValueError, json.JSONDecodeError):
                self._send(401, {"ok": False, "error": "pairing authentication required"})
            return
        if not self._auth():
            self._send(401, {"ok": False, "error": "authentication required"})
            return
        try:
            if path.startswith("/jobs/") and path.endswith("/cancel"):
                job_id = unquote(
                    path.removeprefix("/jobs/").removesuffix("/cancel").rstrip("/")
                )
                self._send(200, self.core.cancel_job(job_id))
                return
            if path.startswith("/zotero/staging/"):
                paper_uid = unquote(path.removeprefix("/zotero/staging/"))
                self._send(200, self.core.stage_pdf_chunk(
                    paper_uid,
                    self._raw_body(),
                    offset=self.headers.get("X-PaperFlow-Offset", "0"),
                    total=self.headers.get("X-PaperFlow-Total", "0"),
                    expected_sha256=self.headers.get("X-PaperFlow-Sha256", ""),
                    filename=self.headers.get("X-PaperFlow-Filename", "paper.pdf"),
                    item_key=self.headers.get("X-PaperFlow-Item-Key", ""),
                ))
                return
            body = self._body()
            if path == "/zotero/events":
                self._send(202, self.core.accept_event(body))
                return
            if path == "/zotero/pairings":
                self._send(201, self.core.create_pairing(body))
                return
            if path == "/zotero/papers/import":
                self._send(200, self.core.import_paper(body))
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
            if path == "/subscriptions/inbox/decision":
                self._send(200, self.core.subscription_decision(body))
                return
            if path == "/community/publish-plan":
                self._send(200, self.core.community_plan(body))
                return
            if path == "/community/publish":
                self._send(200, self.core.community_publish(body))
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
        self.active_job_cancel = threading.Event()
        self.active_cancellation_token = CancellationToken(self.active_job_cancel)
        self.jobs: queue.Queue[dict[str, Any]] = queue.Queue()
        self.job_state_lock = threading.RLock()
        self.stage_lock = threading.RLock()
        self.pending_jobs_loaded = False
        self.active_job_id: str | None = None
        self.lifecycle_state = "stopped"
        self.accepting_jobs = True

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
            "status": self.lifecycle_state,
            "active_job": self.active_job_id,
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
                "started_at": iso_utc(),
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

    @property
    def pairings_path(self) -> Path:
        return state_root(self.root) / PAIRINGS_FILE

    def _read_pairings(self) -> dict[str, Any]:
        try:
            value = json.loads(self.pairings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema_version": 1, "pairings": {}}
        if not isinstance(value, dict) or not isinstance(value.get("pairings"), dict):
            return {"schema_version": 1, "pairings": {}}
        return value

    def _write_pairings(self, value: dict[str, Any]) -> None:
        PermissionGuard(self.root).authorize(self.pairings_path, "SYSTEM_MANAGED")
        atomic_json(self.pairings_path, value)

    def create_pairing(self, body: dict[str, Any]) -> dict[str, Any]:
        allowed = {"client_name"}
        unknown = sorted(set(body) - allowed)
        if unknown:
            raise ValueError(f"unsupported pairing fields: {', '.join(unknown)}")
        client_name = str(body.get("client_name") or "PaperFlow for Zotero").strip()
        if not client_name or len(client_name) > 120:
            raise ValueError("invalid pairing client name")
        pairing_id = secrets.token_hex(12)
        pairing_secret = secrets.token_urlsafe(32)
        value = self._read_pairings()
        pairings = value.setdefault("pairings", {})
        if len(pairings) >= 16:
            oldest = min(
                pairings,
                key=lambda key: str(pairings[key].get("created_at") or ""),
            )
            pairings.pop(oldest, None)
        now = iso_utc()
        pairings[pairing_id] = {
            "client_name": client_name,
            "secret_sha256": hashlib.sha256(pairing_secret.encode("utf-8")).hexdigest(),
            "created_at": now,
            "last_used_at": now,
        }
        value["updated_at"] = now
        self._write_pairings(value)
        return {
            "ok": True,
            "pairing_id": pairing_id,
            "pairing_secret": pairing_secret,
            "created_at": now,
        }

    def refresh_session(self, body: dict[str, Any]) -> dict[str, Any]:
        allowed = {"pairing_id", "pairing_secret"}
        unknown = sorted(set(body) - allowed)
        if unknown:
            raise ValueError(f"unsupported session refresh fields: {', '.join(unknown)}")
        pairing_id = str(body.get("pairing_id") or "").strip()
        pairing_secret = str(body.get("pairing_secret") or "").strip()
        if not pairing_id or not pairing_secret:
            raise ValueError("pairing credentials are required")
        value = self._read_pairings()
        record = value.get("pairings", {}).get(pairing_id)
        if not isinstance(record, dict):
            raise ValueError("invalid pairing credentials")
        actual = hashlib.sha256(pairing_secret.encode("utf-8")).hexdigest()
        expected = str(record.get("secret_sha256") or "")
        if not expected or not hmac.compare_digest(actual, expected):
            raise ValueError("invalid pairing credentials")
        now = iso_utc()
        record["last_used_at"] = now
        value["updated_at"] = now
        self._write_pairings(value)
        return {
            "ok": True,
            "session_token": self.token,
            "issued_at": now,
            "network_scope": "loopback-only",
        }

    def _start_worker(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.worker_stop.clear()
        self._load_pending_jobs()
        self.worker = threading.Thread(
            target=self._worker_loop,
            name="paperflow-core-jobs",
            daemon=True,
        )
        self.worker.start()

    def _load_pending_jobs(self) -> None:
        """Recover queued jobs exactly once after a service restart."""

        with self.job_state_lock:
            if self.pending_jobs_loaded:
                return
            self.pending_jobs_loaded = True
            for path in sorted(_job_root(self.root).glob("*.json")):
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
                if not isinstance(value, dict):
                    continue
                if value.get("status") in {"running", "cancellation-requested"}:
                    value.update(
                        {
                            "status": "interrupted",
                            "finished_at": iso_utc(),
                            "updated_at": iso_utc(),
                            "error": "Core stopped while this job was running",
                        }
                    )
                    _write_job_state(self.root, value)
                    continue
                if value.get("status") == "queued":
                    self.jobs.put({
                        key: value.get(key)
                        for key in (
                            "job_id", "kind", "paper_uid", "provider", "model",
                            "analysis_profile", "zotero_item_key", "target", "source_names",
                        )
                        if key in value
                    })

    def _update_job_state(self, job_id: str, **updates: Any) -> dict[str, Any]:
        with self.job_state_lock:
            value = _read_job_state(self.root, job_id)
            current = str(value.get("status") or "")
            target = str(updates.get("status") or current)
            if target != current and target not in JOB_TRANSITIONS.get(current, set()):
                raise ValueError(f"invalid job state transition: {current} -> {target}")
            value.update(updates)
            value["updated_at"] = iso_utc()
            _write_job_state(self.root, value)
            return value

    def _worker_loop(self) -> None:
        while not self.worker_stop.is_set():
            try:
                job = self.jobs.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                try:
                    state = _read_job_state(
                        self.root, str(job.get("job_id") or "")
                    )
                except FileNotFoundError:
                    continue
                if state.get("status") != "queued":
                    continue
                self.active_job_id = str(job.get("job_id") or "")
                self.active_job_cancel.clear()
                try:
                    self._run_job(job)
                finally:
                    self.active_job_id = None
                    self.active_job_cancel.clear()
            finally:
                self.jobs.task_done()

    def _run_job(self, job: dict[str, Any]) -> None:
        job_id = str(job.get("job_id") or "")
        kind = str(job.get("kind") or "")
        paper_uid = str(job.get("paper_uid") or "")
        self.active_job_id = job_id
        self.active_job_cancel.clear()
        token = self.active_cancellation_token
        self._update_job_state(
            job_id,
            status="running",
            started_at=iso_utc(),
        )
        _append_event(self.root, "jobs", {"job_id": job_id, "kind": kind, "paper_uid": paper_uid, "status": "running"})
        result: dict[str, Any] = {"job_id": job_id, "kind": kind, "paper_uid": paper_uid}
        try:
            token.raise_if_cancelled()
            workspace = self.root / ".paperflow/workspace.yaml"
            if standalone(self.root):
                if kind == "analysis":
                    from paperflow.zotero.standalone_ai import analyze_standalone

                    token.raise_if_cancelled()
                    value = analyze_standalone(
                        self.root,
                        paper_uid,
                        provider_override=str(job.get("provider") or ""),
                        profile_override=str(job.get("analysis_profile") or ""),
                        model_override=str(job.get("model") or ""),
                        cancellation_token=token,
                    )
                    if isinstance(value, dict) and value.get("status") == "aborted":
                        raise JobCancelled("analysis acknowledged cancellation")
                    token.raise_if_cancelled(side_effects=True)
                    if job.get("target") in {"zotero", "obsidian", "both"}:
                        from paperflow.zotero.markdown import render_ai_projection

                        token.raise_if_cancelled()
                        value = {
                            "analysis": value,
                            "ai_projection": render_ai_projection(
                                self.root,
                                paper_uid,
                                zotero_item_key=str(job.get("zotero_item_key") or ""),
                                target=str(job["target"]),
                                apply_changes=True,
                                cancellation_token=token,
                            ),
                        }
                        token.raise_if_cancelled(side_effects=True)
                    result.update({"status": "completed", "result": value})
                elif kind == "render":
                    from paperflow.zotero.markdown import render_ai_projection

                    token.raise_if_cancelled()
                    value = render_ai_projection(
                        self.root,
                        paper_uid,
                        zotero_item_key=str(job.get("zotero_item_key") or ""),
                        target=str(job.get("target") or "zotero"),
                        apply_changes=True,
                        cancellation_token=token,
                    )
                    token.raise_if_cancelled(side_effects=True)
                    result.update({"status": "completed", "result": value})
                elif kind == "subscription-sync":
                    from paperflow.zotero.standalone_sync import sync_core_feed

                    config_path = self.root / "config.yaml"
                    config_value: dict[str, Any] = {}
                    if config_path.is_file():
                        from ruamel.yaml import YAML

                        loaded = YAML(typ="safe").load(config_path.read_text(encoding="utf-8"))
                        if isinstance(loaded, dict):
                            config_value = loaded
                    requested = {
                        str(value).strip()
                        for value in (job.get("source_names") or [])
                        if str(value).strip()
                    }
                    configured = (config_value.get("subscriptions") or {}).get("sources") or []
                    standalone_sources: list[dict[str, Any]] = []
                    for source in configured:
                        if not isinstance(source, dict) or not source.get("url"):
                            continue
                        source_name = str(source.get("name") or source.get("url"))
                        if requested and source_name not in requested:
                            continue
                        standalone_sources.append(source)
                    results = []
                    for source in standalone_sources:
                        token.raise_if_cancelled()
                        results.append(
                            sync_core_feed(
                                self.root,
                                url=str(source["url"]),
                                name=str(source.get("name") or source["url"]),
                                branch=str(source.get("branch") or "main"),
                                trust=str(source.get("trust") or "metadata-and-ai"),
                                dry_run=False,
                                auto_download_pdf=bool(source.get("auto_download_pdf", False)),
                                auto_render_notes=bool(source.get("auto_render_notes", False)),
                                capabilities=list(source.get("capabilities") or ["raw", "ai"]),
                                cancellation_token=token,
                            )
                        )
                        token.raise_if_cancelled(side_effects=True)
                    result.update({"status": "completed", "sources": results, "source_count": len(standalone_sources)})
                else:
                    result.update({"status": "skipped", "reason": "standalone-worker-not-implemented"})
            elif not workspace.is_file():
                result.update({"status": "skipped", "reason": "workspace-not-configured"})
            elif kind == "subscription-sync":
                from paperflow.config import load_config
                from paperflow.feed.subscriber import sync_feed
                from paperflow.locking import FileLock
                from paperflow.workspace import load_workspace_settings

                config = load_config(self.root)
                _, settings = load_workspace_settings(self.root)
                requested = {str(value).strip() for value in (job.get("source_names") or []) if str(value).strip()}
                vault_sources = [source for source in settings.subscriptions.sources if source.enabled and (not requested or source.name in requested)]
                results = []
                with FileLock(self.root / ".paperflow/runtime/pipeline.lock"):
                    for source in vault_sources:
                        token.raise_if_cancelled()
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
                            cancellation_token=token,
                        ))
                        token.raise_if_cancelled(side_effects=True)
                result.update({"status": "completed", "sources": results, "source_count": len(vault_sources)})
            elif kind in {"analysis", "render"}:
                from paperflow.config import ensure_layout, load_config
                from paperflow.locking import FileLock
                from paperflow.pipeline.analyze import analyze_uid
                from paperflow.pipeline.render import render_uid

                config = load_config(self.root)
                ensure_layout(config)
                with FileLock(self.root / ".paperflow/runtime/pipeline.lock"):
                    if kind == "analysis":
                        token.raise_if_cancelled()
                        analysis_value = analyze_uid(
                            config,
                            paper_uid,
                            provider=job.get("provider"),
                            cancellation_token=token,
                        )
                        token.raise_if_cancelled(side_effects=True)
                        render_value = render_uid(
                            config, paper_uid, cancellation_token=token
                        )
                        token.raise_if_cancelled(side_effects=True)
                        pipeline_value: Any = {
                            "analysis": str(analysis_value),
                            "obsidian_projection": str(render_value),
                        }
                    else:
                        token.raise_if_cancelled()
                        pipeline_value = render_uid(
                            config, paper_uid, cancellation_token=token
                        )
                        token.raise_if_cancelled(side_effects=True)
                    if job.get("target") in {"zotero", "obsidian", "both"}:
                        from paperflow.zotero.markdown import render_ai_projection
                        token.raise_if_cancelled()
                        pipeline_value = {
                            "pipeline": pipeline_value,
                            "ai_projection": render_ai_projection(
                                self.root,
                                paper_uid,
                                zotero_item_key=str(job.get("zotero_item_key") or ""),
                                target=str(job["target"]),
                                apply_changes=True,
                                cancellation_token=token,
                            ),
                        }
                        token.raise_if_cancelled(side_effects=True)
                result.update({"status": "completed", "result": str(pipeline_value)})
            else:
                result.update({"status": "skipped", "reason": "worker-not-implemented"})
        except JobCancelled as exc:
            result.update({"status": "cancelled", "reason": str(exc)})
        except JobCompletedAfterCancel as exc:
            result.update(
                {
                    "status": "completed-after-cancel-request",
                    "reason": str(exc),
                }
            )
        except Exception as exc:  # worker failures remain observable and do not kill Core
            result.update({"status": "failed", "error": str(exc)})
        persisted_result = result.get("result")
        if persisted_result is None:
            persisted_result = {
                key: value
                for key, value in result.items()
                if key not in {"job_id", "kind", "paper_uid", "status"}
            }
        self._update_job_state(
            job_id,
            status=str(result.get("status") or "failed"),
            finished_at=iso_utc(),
            result=persisted_result,
        )
        _append_event(self.root, "jobs", result)
        self.active_job_id = None
        self.active_job_cancel.clear()

    def start(self, *, background: bool = True) -> dict[str, Any]:
        if self.httpd is not None:
            return {**self.health(), "started": False, "status": "already-running"}
        self.lifecycle_state = "starting"
        self.accepting_jobs = True
        self.httpd = ThreadingHTTPServer((self.host, self.requested_port), _Handler)
        self.httpd.core = self  # type: ignore[attr-defined]
        session = self._write_session()
        self._write_pairing_token()
        if background:
            self.thread = threading.Thread(target=self.httpd.serve_forever, name="paperflow-core", daemon=True)
            self.thread.start()
        self._start_worker()
        self.lifecycle_state = "ready"
        return {**self.health(), "started": True, "session_state": session.relative_to(self.root).as_posix()}

    def serve_forever(self) -> None:
        if self.httpd is None:
            self.httpd = ThreadingHTTPServer((self.host, self.requested_port), _Handler)
            self.httpd.core = self  # type: ignore[attr-defined]
            self._write_session()
            self._write_pairing_token()
            self._start_worker()
            self.lifecycle_state = "ready"
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

    def stop(
        self,
        *,
        wait: bool = True,
        timeout_seconds: float = 30,
        force: bool = False,
    ) -> dict[str, Any]:
        if self.httpd is None:
            self.lifecycle_state = "stopped"
            return StopResult(status="stopped").as_dict()
        self.lifecycle_state = "stopping"
        self.accepting_jobs = False
        self.worker_stop.set()
        if self.active_job_id:
            self.active_job_cancel.set()
        if wait and self.worker and self.worker is not threading.current_thread():
            self.worker.join(timeout=max(0.0, float(timeout_seconds)))
        if self.worker and self.worker.is_alive():
            # Python threads cannot be force-killed safely. `force` is kept in
            # the API so callers can explicitly learn that process exit is
            # required without the service claiming a false stopped state.
            self.lifecycle_state = "stopping"
            return StopResult(
                status="stopping",
                active_job=self.active_job_id,
                process_exit_required=True,
            ).as_dict()
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
        self.jobs = queue.Queue()
        self.pending_jobs_loaded = False
        self.lifecycle_state = "stopped"
        return StopResult(status="stopped").as_dict()

    def paper(self, paper_uid: str) -> dict[str, Any]:
        path = _paper_path(self.root, paper_uid)
        if not path.is_file():
            return {"ok": False, "paper_uid": paper_uid, "status": "not-found"}
        value = json.loads(path.read_text(encoding="utf-8"))
        return {"ok": True, "paper_uid": paper_uid, "paper": value}

    def paper_pdf(self, paper_uid: str) -> ServedPdf:
        """Return one canonical PDF without accepting a caller-supplied path."""
        paper = self.paper(paper_uid)
        if not paper.get("ok"):
            raise FileNotFoundError(f"paper not found: {paper_uid}")
        paper_value = paper.get("paper")
        record: dict[str, Any] = paper_value if isinstance(paper_value, dict) else {}
        relative = str(record.get("paper_pdf_path") or "").strip()
        if not relative:
            raise FileNotFoundError(f"canonical PDF not found: {paper_uid}")
        target = (self.root / relative).resolve()
        if not target.is_relative_to(self.root) or target.suffix.casefold() != ".pdf":
            raise ValueError("canonical PDF path is invalid")
        if not target.is_file():
            raise FileNotFoundError(f"canonical PDF not found: {paper_uid}")
        size = target.stat().st_size
        if size <= 5 or size > MAX_PDF_BYTES:
            raise ValueError("canonical PDF is empty or exceeds 100 MB")
        with target.open("rb") as stream:
            header = stream.read(5)
        if header != b"%PDF-":
            raise ValueError("canonical document is not a PDF")
        return ServedPdf(
            path=target,
            filename=f"{_paper_component(paper_uid)}.pdf",
            sha256=sha256_file(target),
            size=size,
        )

    def ai_markdown(self, paper_uid: str, *, item_key: str = "") -> dict[str, Any]:
        """Return rendered AI Markdown without writing to Zotero or the Vault."""
        from paperflow.zotero.markdown import _paper_record, build_ai_markdown

        record = _paper_record(self.root, paper_uid)
        body = build_ai_markdown(record, zotero_item_key=item_key)
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        return {
            "ok": True,
            "paper_uid": paper_uid,
            "item_key": item_key,
            "content": body,
            "content_sha256": digest,
            "filename": f"{_paper_component(paper_uid)}.analysis.md",
            "artifact_permission": "USER_EDITABLE_PROJECTION",
        }

    def import_paper(self, body: dict[str, Any]) -> dict[str, Any]:
        """Import a PaperMetadata snapshot supplied by the Zotero plugin.

        This is an append/merge operation: existing canonical records are not
        overwritten with empty Zotero fields, and conflicting non-empty values
        are preserved in a review snapshot instead of silently replaced.
        """
        paper_snapshot = body.get("paper")
        snapshot: dict[str, Any] = paper_snapshot if isinstance(paper_snapshot, dict) else body
        value = _canonical_paper_from_snapshot(snapshot)
        paper_uid = str(value["paper_uid"])
        target = _paper_path(self.root, paper_uid)
        target.parent.mkdir(parents=True, exist_ok=True)
        conflicts: dict[str, dict[str, Any]] = {}
        if target.is_file():
            try:
                existing = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"existing paper record is invalid: {target}") from exc
            if not isinstance(existing, dict):
                raise ValueError("existing paper record must be an object")
            conflicts = {
                key: {"existing": existing[key], "incoming": value[key]}
                for key in value
                if key in existing and existing[key] not in ("", [], None)
                and value[key] not in ("", [], None)
                and existing[key] != value[key]
                and key not in {"artifact_permission"}
            }
            merged = dict(existing)
            for key, incoming in value.items():
                if key not in merged or merged[key] in ("", [], None):
                    merged[key] = incoming
            if conflicts:
                review = runtime_root(self.root) / "manual-review" / f"{_paper_component(paper_uid)}-zotero-import.json"
                review.parent.mkdir(parents=True, exist_ok=True)
                atomic_json(review, {"paper_uid": paper_uid, "conflicts": conflicts, "incoming": value})
            value = merged
            if merged != existing:
                PermissionGuard(self.root).authorize(target, "RAW_VERSIONED")
                atomic_json(target, merged)
            status = "reused" if not conflicts else "manual-review"
        else:
            PermissionGuard(self.root).authorize(target, "RAW_VERSIONED")
            atomic_json(target, value)
            status = "imported"
        return {
            "ok": True,
            "paper_uid": paper_uid,
            "status": status,
            "path": target.relative_to(self.root).as_posix(),
            "conflicts": sorted(conflicts),
        }

    def stage_pdf_chunk(
        self,
        paper_uid: str,
        chunk: bytes,
        *,
        offset: str,
        total: str,
        expected_sha256: str,
        filename: str,
        item_key: str = "",
    ) -> dict[str, Any]:
        """Receive a PDF through authenticated loopback chunks.

        Zotero reads the attachment with its public object API and sends only
        bytes to this endpoint.  Core never receives a Zotero filesystem path.
        The final file is hash-checked and atomically promoted to the
        standalone ``documents/zotero`` area.
        """
        component = _paper_component(paper_uid)
        try:
            start = int(offset)
            size = int(total)
        except (TypeError, ValueError) as exc:
            raise ValueError("offset and total must be integers") from exc
        digest = str(expected_sha256 or "").strip().lower()
        if start < 0 or size <= 0 or size > MAX_PDF_BYTES or start > size:
            raise ValueError("invalid PDF upload range")
        if len(chunk) > MAX_PDF_CHUNK_BYTES or start + len(chunk) > size:
            raise ValueError("PDF chunk is too large")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("expected_sha256 must be a SHA-256 hex digest")
        safe_name = safe_component(Path(str(filename or "paper.pdf")).name)
        if not safe_name.lower().endswith(".pdf"):
            safe_name += ".pdf"
        staging = runtime_root(self.root) / "staging" / "zotero" / component
        part = staging / f"{safe_name}.part"
        with self.stage_lock:
            staging.mkdir(parents=True, exist_ok=True)
            current = part.stat().st_size if part.is_file() else 0
            if current != start:
                raise ValueError(f"unexpected PDF upload offset: expected {current}, got {start}")
            mode = "wb" if start == 0 else "ab"
            with part.open(mode) as stream:
                stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            uploaded = part.stat().st_size
            if uploaded < size:
                return {"ok": True, "status": "staging", "paper_uid": paper_uid, "offset": uploaded, "total": size}
            with part.open("rb") as stream:
                header = stream.read(5)
            if uploaded != size or header != b"%PDF-":
                part.unlink(missing_ok=True)
                raise ValueError("staged file is not a complete PDF")
            actual = sha256_file(part)
            if not hmac.compare_digest(actual, digest):
                part.unlink(missing_ok=True)
                raise ValueError("staged PDF SHA-256 mismatch")
            documents = self.root / "documents/zotero"
            documents.mkdir(parents=True, exist_ok=True)
            target = documents / f"{component}.pdf"
            if target.is_file():
                existing = sha256_file(target)
                if existing != actual:
                    conflict = target.with_name(f"{target.stem}-conflict-{actual[:12]}{target.suffix}")
                    part.replace(conflict)
                    return {"ok": True, "status": "manual-review", "paper_uid": paper_uid, "path": conflict.relative_to(self.root).as_posix(), "sha256": actual}
                part.unlink(missing_ok=True)
                final_path = target
                status = "reused"
            else:
                PermissionGuard(self.root).authorize(target, "RAW_VERSIONED")
                part.replace(target)
                final_path = target
                status = "stored"
            paper_path = _paper_path(self.root, paper_uid)
            if paper_path.is_file():
                record = json.loads(paper_path.read_text(encoding="utf-8"))
                if isinstance(record, dict) and not record.get("paper_pdf_path"):
                    record["paper_pdf_path"] = final_path.relative_to(self.root).as_posix()
                    atomic_json(paper_path, record)
            return {"ok": True, "status": status, "paper_uid": paper_uid, "path": final_path.relative_to(self.root).as_posix(), "sha256": actual, "item_key": item_key}

    def item_status(self, item_key: str) -> dict[str, Any]:
        if not item_key or len(item_key) > 80 or not item_key.replace("-", "").isalnum():
            raise ValueError("invalid Zotero item key")
        value = mapping_for_item(self.root, item_key)
        if value is not None:
            return {"ok": True, "item_key": item_key, "linked": True, "mapping": value}
        return {"ok": True, "item_key": item_key, "linked": False, "status": "unlinked"}

    def _mapping_for_item(self, item_key: str) -> dict[str, Any] | None:
        return mapping_for_item(self.root, item_key)

    def _analysis_summary(self, paper_uid: str) -> dict[str, Any]:
        """Return a bounded analysis summary without exposing raw prompts or paths."""
        record: dict[str, Any] | None = None
        try:
            from paperflow.zotero.standalone_ai import load_current_analysis

            record = load_current_analysis(self.root, paper_uid)
        except (OSError, ValueError, ImportError):
            record = None
        if record is None:
            base = data_root(self.root) / "ai"
            component = safe_component(paper_uid.replace(":", "_"))
            candidates = sorted(base.glob(f"*/{component}/v*/*.json"), key=lambda path: path.stat().st_mtime)
            for candidate in reversed(candidates):
                if candidate.name == "current.json":
                    continue
                try:
                    value = json.loads(candidate.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict) and value.get("paper_uid") == paper_uid:
                    record = value
                    break
        if not isinstance(record, dict):
            return {"status": "not-analyzed"}
        identity_value = record.get("identity")
        identity: dict[str, Any] = identity_value if isinstance(identity_value, dict) else {}
        analysis_value = record.get("analysis")
        analysis: dict[str, Any] = analysis_value if isinstance(analysis_value, dict) else {}
        summary_keys = (
            "ai_summary_short", "ai_one_sentence_summary", "ai_reading_recommendation",
            "ai_method_family", "ai_contributions", "ai_experimental_findings",
            "ai_limitations", "ai_feynman_questions",
        )
        summary = {key: analysis[key] for key in summary_keys if key in analysis}
        return {
            "status": str(record.get("status") or "complete"),
            "provider": str(identity.get("provider") or ""),
            "model": str(identity.get("model") or ""),
            "profile": str(identity.get("profile") or ""),
            "prompt_version": str(identity.get("prompt_version") or ""),
            "analyzed_at": str(record.get("analyzed_at") or ""),
            "analysis_id": str(record.get("analysis_id") or ""),
            "summary": summary,
        }

    def item_workspace(self, item_key: str) -> dict[str, Any]:
        if not item_key or len(item_key) > 80 or not item_key.replace("-", "").isalnum():
            raise ValueError("invalid Zotero item key")
        mapping = self._mapping_for_item(item_key)
        paper_uid = str(mapping.get("paper_uid") or "") if mapping else ""
        paper = self.paper(paper_uid).get("paper") if paper_uid else None
        annotations = self.annotation_list(paper_uid) if paper_uid else {"count": 0, "active_count": 0, "annotations": []}
        feynman: dict[str, Any] = {"question_count": 0, "answered_count": 0}
        if paper_uid:
            try:
                from paperflow.zotero.feynman import load_answers

                answers = load_answers(self.root, paper_uid)
                question_value = answers.get("questions")
                questions: list[Any] = question_value if isinstance(question_value, list) else []
                answer_value = answers.get("answers")
                answer_map: dict[str, Any] = answer_value if isinstance(answer_value, dict) else {}
                feynman = {"question_count": len(questions), "answered_count": len(answer_map)}
            except (OSError, ValueError, ImportError):
                pass
        jobs = self.list_jobs(limit=200).get("jobs", [])
        recent_jobs = [
            {key: job.get(key) for key in ("job_id", "kind", "status", "provider", "analysis_profile", "created_at", "updated_at", "error") if key in job}
            for job in jobs if paper_uid and job.get("paper_uid") == paper_uid
        ][:10]
        subscription = self.subscription_inbox_item(paper_uid) if paper_uid else {"status": "not-linked"}
        community = self.community_paper(paper_uid) if paper_uid else {"count": 0, "items": []}
        return {
            "ok": True,
            "item_key": item_key,
            "linked": bool(mapping and paper_uid),
            "paper_uid": paper_uid,
            "paper": paper,
            "mapping": mapping,
            "analysis": self._analysis_summary(paper_uid) if paper_uid else {"status": "not-linked"},
            "annotations": {"count": annotations.get("count", 0), "active_count": annotations.get("active_count", 0)},
            "feynman": feynman,
            "subscription": {key: subscription.get(key) for key in ("status", "source", "feed_id", "updated_at") if key in subscription},
            "community": community,
            "recent_jobs": recent_jobs,
            "diagnostics": {"core": "online", "permission": "read-only-summary"},
        }

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

    def _subscription_inbox_root(self) -> Path:
        """Return the canonical Inbox directory, with a one-way legacy fallback.

        Older standalone fixtures used ``<root>/data`` while a Vault-backed
        service uses ``<vault>/.paperflow/data``.  Prefer the configured
        canonical path; only consult the old path when it is already present
        and the canonical directory has not been created.  This keeps a Vault
        from accidentally merging arbitrary top-level data while allowing an
        existing Inbox to be read during migration.
        """
        canonical = data_root(self.root) / "subscriptions/inbox"
        legacy = self.root / "data/subscriptions/inbox"
        if canonical.is_dir() or not legacy.is_dir() or canonical == legacy:
            return canonical
        return legacy

    @staticmethod
    def _subscription_paper(value: dict[str, Any]) -> dict[str, Any]:
        paper_uid = str(value.get("paper_uid") or "")
        source_id = str(value.get("source_id") or "")
        source = str(value.get("source") or "").strip().lower()
        arxiv_id = ""
        if source_id.startswith("arxiv_"):
            arxiv_id = source_id.removeprefix("arxiv_")
        elif source_id.startswith("arxiv:"):
            arxiv_id = source_id.removeprefix("arxiv:")
        elif paper_uid.startswith("arxiv:"):
            arxiv_id = paper_uid.removeprefix("arxiv:")
        elif source == "arxiv" and source_id:
            arxiv_id = source_id
        version = value.get("source_version") or value.get("version") or 1
        try:
            version = max(1, int(version))
        except (TypeError, ValueError):
            version = 1
        paper_source = "arxiv" if arxiv_id else ("doi" if paper_uid.startswith("doi:") or source == "doi" else source or "unknown")
        return {
            "paper_uid": paper_uid,
            "paper_source": paper_source,
            "paper_arxiv_id": arxiv_id,
            "paper_arxiv_version": version,
            "paper_title": str(value.get("title") or ""),
            "paper_authors": value.get("authors") if isinstance(value.get("authors"), list) else [],
            "paper_abstract": str(value.get("abstract") or ""),
            "paper_abs_url": str(value.get("url") or ""),
            "paper_pdf_url": str(((value.get("pdf") or {}).get("source_url") if isinstance(value.get("pdf"), dict) else "") or ""),
        }

    @classmethod
    def _public_subscription_record(cls, value: dict[str, Any]) -> dict[str, Any]:
        # Never expose local source paths or hashes through the Zotero UI API.
        public: dict[str, Any] = {
            key: value.get(key)
            for key in (
                "schema_version", "artifact_permission", "paper_uid", "title", "authors",
                "abstract", "url", "source", "source_id", "source_version", "feed_id", "pdf", "status", "created_at",
                "updated_at", "decision_at", "zotero_item_key", "decision_note",
            )
            if key in value
        }
        public["paper"] = cls._subscription_paper(value)
        return public

    def subscription_inbox(self, *, limit: int = 100, status: str = "") -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        expected_status = str(status or "").strip().lower()
        for path in sorted(self._subscription_inbox_root().glob("*.json")) if self._subscription_inbox_root().is_dir() else []:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict) or not value.get("paper_uid"):
                continue
            if expected_status and str(value.get("status") or "").lower() != expected_status:
                continue
            records.append(self._public_subscription_record(value))
        records.sort(key=lambda value: str(value.get("updated_at") or ""), reverse=True)
        counts: dict[str, int] = {}
        for value in records:
            key = str(value.get("status") or "unknown")
            counts[key] = counts.get(key, 0) + 1
        return {"ok": True, "count": len(records), "counts": counts, "items": records[: max(1, min(500, int(limit)))]}

    def subscription_inbox_item(self, paper_uid: str) -> dict[str, Any]:
        component = _paper_component(paper_uid)
        target = self._subscription_inbox_root() / f"{component}.json"
        if not target.is_file():
            return {"ok": False, "paper_uid": paper_uid, "status": "not-found"}
        value = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("subscription inbox record must be an object")
        return {"ok": True, **self._public_subscription_record(value)}

    def subscription_status(self) -> dict[str, Any]:
        inbox = self.subscription_inbox(limit=500)
        return {
            "ok": True,
            "count": inbox.get("count", 0),
            "counts": inbox.get("counts", {}),
            "last_updated_at": max(
                (str(item.get("updated_at") or "") for item in inbox.get("items", [])),
                default="",
            ),
        }

    def community_paper(self, paper_uid: str) -> dict[str, Any]:
        _paper_component(paper_uid)
        roots = [
            data_root(self.root) / "community/subscriptions",
            data_root(self.root) / "community/outbox",
        ]
        items: list[dict[str, Any]] = []
        for root in roots:
            if not root.is_dir():
                continue
            paper_component = safe_component(paper_uid.replace(":", "_"))
            # Subscription feeds include a feed-id directory, while the
            # local outbox is intentionally flatter. Read both layouts.
            paths: list[Path] = []
            for pattern in (
                f"*/papers/{paper_component}/community/*/*/r*.json",
                f"papers/{paper_component}/community/*/*/r*.json",
            ):
                paths.extend(root.glob(pattern))
            for path in paths:
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(value, dict) or value.get("paper_uid") != paper_uid:
                    continue
                # The Zotero pane gets enough context to navigate/filter, but
                # never receives a local path or an unbounded private payload.
                items.append({
                    key: value.get(key)
                    for key in (
                        "contribution_id", "revision", "creator", "kind", "body",
                        "tags", "license", "created_at", "content_sha256", "anchor",
                    ) if key in value
                })
        unique = {(str(item.get("creator")), str(item.get("contribution_id")), int(item.get("revision") or 0)): item for item in items}
        records = sorted(unique.values(), key=lambda item: (str(item.get("created_at") or ""), str(item.get("contribution_id") or "")), reverse=True)
        return {"ok": True, "paper_uid": paper_uid, "count": len(records), "items": records[:100]}

    def subscription_decision(self, body: dict[str, Any]) -> dict[str, Any]:
        allowed = {"paper_uid", "decision", "item_key", "note"}
        unknown = sorted(set(body) - allowed)
        if unknown:
            raise ValueError(f"unsupported subscription decision fields: {', '.join(unknown)}")
        paper_uid = str(body.get("paper_uid") or "").strip()
        component = _paper_component(paper_uid)
        decision = str(body.get("decision") or "").strip().lower()
        if decision not in {"approve", "imported", "dismiss"}:
            raise ValueError("decision must be approve, imported, or dismiss")
        item_key = str(body.get("item_key") or "").strip()
        if decision == "imported" and (not item_key or len(item_key) > 80 or not item_key.replace("-", "").isalnum()):
            raise ValueError("imported decision requires a valid Zotero item key")
        target = self._subscription_inbox_root() / f"{component}.json"
        if not target.is_file():
            raise FileNotFoundError(f"subscription inbox item not found: {paper_uid}")
        value = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("paper_uid") != paper_uid:
            raise ValueError("subscription inbox identity mismatch")
        value["status"] = {"approve": "approved", "imported": "imported", "dismiss": "dismissed"}[decision]
        value["updated_at"] = iso_utc()
        value["decision_at"] = value["updated_at"]
        if item_key:
            value["zotero_item_key"] = item_key
        if body.get("note") is not None:
            value["decision_note"] = str(body.get("note") or "")[:1000]
        PermissionGuard(self.root).authorize(target, "SYSTEM_MANAGED")
        atomic_json(target, value)
        return {"ok": True, "decision": decision, **self._public_subscription_record(value)}

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
                value.update({"deleted": True, "updated_at": body.get("updated_at") or iso_utc(), "artifact_permission": "SYSTEM_MANAGED"})
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
            "created_at": str(body.get("created_at") or iso_utc()),
            "updated_at": str(body.get("updated_at") or iso_utc()),
            "deleted": False,
        }
        atomic_json(target, value)
        return {"ok": True, "status": "mirrored", "annotation_id": annotation_id, "paper_uid": paper_uid, "path": target.relative_to(self.root).as_posix(), "permission": "SYSTEM_MANAGED"}

    def _resolve_analysis_request(self, body: dict[str, Any]) -> dict[str, str]:
        """Resolve a UI profile to the provider understood by the pipeline."""
        requested_profile = str(body.get("analysis_profile") or "").strip()
        explicit_provider = str(body.get("provider") or "").strip().lower()
        profile = requested_profile or "full_analysis"
        provider = explicit_provider
        model = str(body.get("model") or "").strip()
        try:
            from paperflow.workspace import load_workspace_settings

            _, settings = load_workspace_settings(self.root)
            if profile not in settings.ai.profiles:
                profile = settings.ai.full_analysis_profile
            selected = settings.ai.profiles.get(profile)
            if selected is not None:
                provider = provider or selected.provider
                model = model or selected.model
        except (OSError, ValueError, KeyError):
            # Standalone roots use their compact config.yaml policy.
            config_path = self.root / "config.yaml"
            try:
                if config_path.is_file():
                    from ruamel.yaml import YAML

                    raw = YAML(typ="safe").load(config_path.read_text(encoding="utf-8"))
                    policy = raw.get("analysis") if isinstance(raw, dict) else {}
                    if isinstance(policy, dict):
                        provider = provider or str(policy.get("provider") or "")
                        model = model or str(policy.get("model") or "")
                        profile = str(policy.get("profile") or profile)
            except (OSError, ValueError):
                pass
        if provider not in {"codex", "claude", "chatgpt-web", "mock", ""}:
            raise ValueError(f"unsupported analysis provider: {provider}")
        return {"analysis_profile": profile, "provider": provider, "model": model}

    def _canonical_analysis_reusable(
        self,
        paper_uid: str,
        pdf_sha256: str,
        analysis_profile: str,
    ) -> bool:
        digest = str(pdf_sha256 or "").strip().lower()
        if not digest:
            return False
        target = _paper_path(self.root, paper_uid)
        try:
            record = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(record, dict):
            return False
        if str(record.get("ai_analysis_status") or "").casefold() != "complete":
            return False
        if str(record.get("system_content_hash") or "").strip().lower() != digest:
            return False
        policy = "identity-changed"
        try:
            from paperflow.workspace import load_workspace_settings

            _, settings = load_workspace_settings(self.root)
            profile = settings.ai.profiles.get(analysis_profile)
            if profile is not None:
                policy = profile.reanalyze_when
        except (OSError, ValueError, KeyError):
            pass
        if policy == "always":
            return False
        if policy == "never":
            return True
        # A matching PDF digest is the stable content identity used by the
        # Zotero event contract. Under identity-changed policy, an existing
        # complete analysis remains authoritative even if it was produced by a
        # fallback profile.
        return True

    def accept_event(self, body: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "item_key", "event", "item_type", "attachment_keys", "timestamp",
            "is_regular", "in_collection", "has_pdf", "pdf_stable",
            "identity_resolved", "pdf_sha256", "analysis_profile", "paper_uid",
            "provider", "model",
        }
        unknown = sorted(set(body) - allowed)
        if unknown:
            raise ValueError(f"unsupported event fields: {', '.join(unknown)}")
        if not body.get("event") or not body.get("item_key"):
            raise ValueError("item_key and event are required")
        request = self._resolve_analysis_request(body)
        reusable = False
        if body.get("paper_uid"):
            reusable = self._canonical_analysis_reusable(
                str(body["paper_uid"]),
                str(body.get("pdf_sha256") or ""),
                str(request["analysis_profile"]),
            )
        pipeline_body = {**body, **request, "analysis_reusable": reusable}
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
        pipeline = ZoteroEventProcessor(self.root, **processor_kwargs).handle(pipeline_body)
        _append_event(self.root, "events", {key: body[key] for key in body if key in allowed})
        queued_job = None
        if pipeline.get("queue_render") and body.get("paper_uid"):
            queued_job = self.enqueue_job(
                "render",
                {
                    "paper_uid": body["paper_uid"],
                    "zotero_item_key": body.get("item_key"),
                    # Vault render_uid is always the canonical Obsidian
                    # projection. The explicit target requests only the
                    # secondary Zotero Markdown artifact.
                    "target": "zotero",
                },
            )
        elif pipeline.get("queue_analysis") and body.get("paper_uid"):
            queued_job = self.enqueue_job(
                "analysis",
                {
                    "paper_uid": body["paper_uid"],
                    "analysis_profile": request["analysis_profile"],
                    "provider": request["provider"] or None,
                    "model": request["model"],
                    "zotero_item_key": body.get("item_key"),
                    "trigger": "zotero-event",
                    "target": "zotero",
                },
            )
        return {"ok": True, "accepted": True, "status": "observed", "pipeline": pipeline, "job": queued_job}

    def enqueue_job(self, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        if not self.accepting_jobs:
            raise ValueError("Core is stopping and does not accept new jobs")
        paper_uid = str(body.get("paper_uid") or "").strip()
        if not paper_uid:
            raise ValueError("paper_uid is required")
        _paper_path(self.root, paper_uid)
        allowed = {
            "paper_uid",
            "provider",
            "model",
            "analysis_profile",
            "zotero_item_key",
            "trigger",
            "target",
            "source_content_hash",
        }
        unknown = sorted(set(body) - allowed)
        if unknown:
            raise ValueError(f"unsupported job fields: {', '.join(unknown)}")
        target = str(body.get("target") or "").strip().lower()
        if target and target not in {"zotero", "obsidian", "both"}:
            raise ValueError("target must be zotero, obsidian, or both")
        request = self._resolve_analysis_request(body) if kind == "analysis" else {"analysis_profile": "", "provider": "", "model": ""}
        provider = str(body.get("provider") or request["provider"] or "")
        model = str(body.get("model") or request["model"] or "")
        analysis_profile = str(body.get("analysis_profile") or request["analysis_profile"] or "full_analysis")
        source_content_hash = str(body.get("source_content_hash") or "")
        idempotency_payload = {
            "kind": kind,
            "paper_uid": paper_uid,
            "provider": provider,
            "model": model,
            "analysis_profile": analysis_profile,
            "source_content_hash": source_content_hash,
            "target": target,
        }
        idempotency_key = hashlib.sha256(
            json.dumps(
                idempotency_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        with self.job_state_lock:
            for path in _job_root(self.root).glob("*.json"):
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
                if (
                    existing.get("idempotency_key") == idempotency_key
                    and existing.get("status") in {"queued", "running", "cancellation-requested"}
                ):
                    return {
                        "ok": True,
                        "job_id": existing["job_id"],
                        "status": existing["status"],
                        "reused": True,
                    }
        job_id = f"zotero-{kind}-{secrets.token_hex(8)}"
        job = {
            "schema_version": JOB_SCHEMA_VERSION,
            "job_id": job_id,
            "kind": kind,
            "paper_uid": paper_uid,
            "provider": provider,
            "model": model,
            "analysis_profile": analysis_profile,
            "zotero_item_key": body.get("zotero_item_key"),
            "target": target,
            "source_content_hash": source_content_hash,
            "idempotency_key": idempotency_key,
            "created_at": iso_utc(),
            "updated_at": iso_utc(),
            "status": "queued",
            "trigger": body.get("trigger", ""),
            "attempt": 0,
            "started_at": None,
            "finished_at": None,
            "error": None,
        }
        _write_job_state(self.root, job)
        _append_event(self.root, "jobs", {**job, "status": "queued", "trigger": body.get("trigger", "")})
        # Before the HTTP service starts, durable state is enough; startup
        # recovery will enqueue it exactly once.  Once recovery has run, new
        # requests can be placed directly on the live queue.
        if self.pending_jobs_loaded:
            self.jobs.put(job)
        return {
            "ok": True,
            "job_id": job_id,
            "status": "queued",
            "reused": False,
        }

    def job(self, job_id: str) -> dict[str, Any]:
        """Return one durable job record for Zotero UI polling."""

        return {"ok": True, **_read_job_state(self.root, job_id)}

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        """Cancel a queued job or request cooperative cancellation of a runner."""

        value = _read_job_state(self.root, job_id)
        status = str(value.get("status") or "")
        if status == "queued":
            updated = self._update_job_state(
                job_id,
                status="cancelled",
                finished_at=iso_utc(),
                cancellation_requested_at=iso_utc(),
                cancelled_at=iso_utc(),
                error=None,
            )
            _append_event(
                self.root,
                "jobs",
                {
                    "job_id": job_id,
                    "kind": updated.get("kind"),
                    "paper_uid": updated.get("paper_uid"),
                    "status": "cancelled",
                },
            )
            return {"ok": True, "job_id": job_id, "status": "cancelled", "cancelled": True}
        if status == "running":
            if self.active_job_id == job_id:
                self.active_job_cancel.set()
            updated = self._update_job_state(
                job_id,
                status="cancellation-requested",
                cancellation_requested_at=iso_utc(),
            )
            return {
                "ok": True,
                "job_id": job_id,
                "status": updated["status"],
                "cancelled": False,
            }
        return {
            "ok": True,
            "job_id": job_id,
            "status": status,
            "cancelled": status == "cancelled",
        }

    def list_jobs(self, *, limit: int = 50) -> dict[str, Any]:
        """Return recent durable jobs without exposing raw paths or prompts."""

        records: list[dict[str, Any]] = []
        for path in _job_root(self.root).glob("*.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and value.get("job_id"):
                records.append(value)
        records.sort(key=lambda value: str(value.get("updated_at") or ""), reverse=True)
        return {"ok": True, "jobs": records[: max(1, min(200, int(limit)))]}

    def community_plan(self, body: dict[str, Any]) -> dict[str, Any]:
        if not body.get("paper_uid"):
            raise ValueError("paper_uid is required")
        value = {
            "ok": True,
            "paper_uid": str(body["paper_uid"]),
            "status": "preview-only",
            "requires_user_confirmation": True,
            "network_changes": 0,
        }
        if body.get("contribution") is not None:
            value["contribution"] = self._community_contribution(body, preview=True)
        return value

    def _community_contribution(self, body: dict[str, Any], *, preview: bool) -> dict[str, Any]:
        from paperflow.community.publisher import immutable_snapshot

        source = body.get("contribution")
        if not isinstance(source, dict):
            raise ValueError("contribution must be an object")
        creator = str(body.get("creator") or source.get("creator") or "").strip()
        license_name = str(body.get("license") or source.get("license") or "").strip()
        if not creator or not license_name:
            raise ValueError("creator and license are required")
        snapshot = immutable_snapshot(
            source,
            creator=creator,
            license_name=license_name,
            revision=int(body.get("revision") or source.get("revision") or 1),
            supersedes=str(body.get("supersedes") or source.get("supersedes") or ""),
        )
        value = snapshot.model_dump(mode="json")
        paper_id = safe_storage_component(value["paper_uid"], label="paper_uid")
        relative = (
            Path("papers")
            / paper_id
            / "community"
            / safe_storage_component(creator, label="creator")
            / safe_storage_component(value["contribution_id"], label="contribution_id")
            / f"r{value['revision']}.json"
        )
        value.update({
            "path": relative.as_posix(),
            "artifact_permission": "PUBLIC_IMMUTABLE",
            "network_changes": 0,
            "requires_user_confirmation": preview,
        })
        return value

    def community_publish(self, body: dict[str, Any]) -> dict[str, Any]:
        if not body.get("paper_uid"):
            raise ValueError("paper_uid is required")
        if body.get("confirm") is not True:
            raise ValueError("community publish requires explicit confirm=true")
        value = self._community_contribution(body, preview=False)
        if str(value.get("paper_uid")) != str(body["paper_uid"]):
            raise ValueError("paper_uid does not match contribution")
        relative = Path(str(value.pop("path")))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("invalid community outbox path")
        target = resolve_under(
            data_root(self.root),
            "community",
            "outbox",
            *relative.parts,
            label="Core Community outbox path",
        )
        stored = dict(value)
        for key in ("path", "artifact_permission", "network_changes", "requires_user_confirmation"):
            stored.pop(key, None)
        PermissionGuard(self.root).authorize(target, "PUBLIC_IMMUTABLE")
        if target.is_file():
            existing = json.loads(target.read_text(encoding="utf-8"))
            if existing != stored:
                raise RuntimeError("immutable community outbox record already exists")
            status = "reused"
        else:
            atomic_json(target, stored)
            status = "outbox-written"
        return {
            "ok": True,
            "paper_uid": str(body["paper_uid"]),
            "status": status,
            "path": target.relative_to(self.root).as_posix(),
            "network_changes": 0,
            "remote_push": "not-automatic",
            "requires_user_confirmation": False,
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
            "schema_version": JOB_SCHEMA_VERSION,
            "job_id": job_id,
            "kind": "subscription-sync",
            "source_names": source_names,
            "created_at": iso_utc(),
            "updated_at": iso_utc(),
            "status": "queued",
            "trigger": body.get("trigger", ""),
        }
        _write_job_state(self.root, job)
        _append_event(self.root, "jobs", {
            "job_id": job_id,
            "kind": "subscription-sync",
            "status": "queued",
            "source": body.get("source", ""),
            "source_names": source_names,
            "trigger": body.get("trigger", ""),
        })
        if self.pending_jobs_loaded:
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
    "PAIRINGS_FILE",
]
