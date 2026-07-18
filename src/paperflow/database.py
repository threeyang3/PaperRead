from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Any
from .utils import iso_beijing

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS papers (paper_uid TEXT PRIMARY KEY, arxiv_id TEXT, version INTEGER, status TEXT, note_path TEXT, json_path TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS paper_versions (paper_uid TEXT, version INTEGER, snapshot_path TEXT, created_at TEXT, PRIMARY KEY(paper_uid, version));
CREATE TABLE IF NOT EXISTS discovery_runs (run_id TEXT PRIMARY KEY, status TEXT, stats_json TEXT, started_at TEXT, finished_at TEXT);
CREATE TABLE IF NOT EXISTS import_jobs (job_id TEXT PRIMARY KEY, paper_uid TEXT, status TEXT, stage TEXT, error TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS analysis_runs (run_id TEXT PRIMARY KEY, paper_uid TEXT, provider TEXT, model TEXT, prompt_version TEXT, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS manual_requests (request_id TEXT PRIMARY KEY, path TEXT, status TEXT, paper_uid TEXT, error TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS failed_jobs (job_id TEXT PRIMARY KEY, payload_json TEXT, attempts INTEGER DEFAULT 0, error TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT);
"""


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)", (1, iso_beijing()))
        self.conn.execute("UPDATE schema_migrations SET applied_at=? WHERE applied_at NOT LIKE '%+08:00'", (iso_beijing(),))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def get_paper(self, uid: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM papers WHERE paper_uid=?", (uid,)).fetchone()
        return dict(row) if row else None

    def upsert_paper(self, record: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO papers(paper_uid,arxiv_id,version,status,note_path,json_path,updated_at) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(paper_uid) DO UPDATE SET version=excluded.version,status=excluded.status,note_path=excluded.note_path,json_path=excluded.json_path,updated_at=excluded.updated_at",
            (record["paper_uid"], record.get("paper_arxiv_id", ""), record.get("paper_arxiv_version", 1), record.get("system_status", "completed"), record.get("note_path", ""), record.get("json_path", ""), iso_beijing()),
        )
        self.conn.commit()

    def record_request(self, request_id: str, path: str, status: str, paper_uid: str = "", error: str = "") -> None:
        self.conn.execute(
            "INSERT INTO manual_requests(request_id,path,status,paper_uid,error,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(request_id) DO UPDATE SET path=excluded.path,status=excluded.status,paper_uid=excluded.paper_uid,error=excluded.error,updated_at=excluded.updated_at",
            (request_id, path, status, paper_uid, error, iso_beijing()),
        )
        self.conn.commit()

    def stats(self) -> dict[str, int]:
        tables = ["papers", "paper_versions", "discovery_runs", "import_jobs", "analysis_runs", "manual_requests", "failed_jobs"]
        return {t: self.conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}

    def add_failed(self, job_id: str, payload: dict[str, Any], error: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO failed_jobs(job_id,payload_json,attempts,error,updated_at) VALUES(?,?,COALESCE((SELECT attempts+1 FROM failed_jobs WHERE job_id=?),1),?,?)", (job_id, json.dumps(payload), job_id, error, iso_beijing()))
        self.conn.commit()

    def record_analysis(self, run_id: str, paper_uid: str, provider: str, model: str, prompt_version: str, status: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO analysis_runs(run_id,paper_uid,provider,model,prompt_version,status,created_at) VALUES(?,?,?,?,?,?,?)", (run_id, paper_uid, provider, model, prompt_version, status, iso_beijing()))
        self.conn.commit()

    def record_version(self, paper_uid: str, version: int, snapshot_path: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO paper_versions(paper_uid,version,snapshot_path,created_at) VALUES(?,?,?,?)", (paper_uid, version, snapshot_path, iso_beijing()))
        self.conn.commit()

    def set_import_job(self, job_id: str, paper_uid: str, status: str, stage: str, error: str = "") -> None:
        self.conn.execute(
            "INSERT INTO import_jobs(job_id,paper_uid,status,stage,error,updated_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(job_id) DO UPDATE SET paper_uid=excluded.paper_uid,status=excluded.status,stage=excluded.stage,error=excluded.error,updated_at=excluded.updated_at",
            (job_id, paper_uid, status, stage, error, iso_beijing()),
        )
        self.conn.commit()

    def apply_migration(self, version: int) -> None:
        self.conn.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(?,?)", (version, iso_beijing()))
        self.conn.commit()

    def record_discovery_run(self, run_id: str, status: str, stats: dict[str, Any], started_at: str, finished_at: str = "") -> None:
        self.conn.execute(
            "INSERT INTO discovery_runs(run_id,status,stats_json,started_at,finished_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(run_id) DO UPDATE SET status=excluded.status,stats_json=excluded.stats_json,finished_at=excluded.finished_at",
            (run_id, status, json.dumps(stats, ensure_ascii=False), started_at, finished_at),
        )
        self.conn.commit()
