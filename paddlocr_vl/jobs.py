from __future__ import annotations

from contextlib import contextmanager
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterator
import uuid

from .core.config import Settings

TERMINAL = {"completed", "failed", "cancelled"}


class QueueFullError(RuntimeError):
    pass


class JobStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.jobs_dir.mkdir(parents=True, exist_ok=True)
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        self.init()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.settings.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    output_format TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    completed_at REAL,
                    last_claimed_at REAL,
                    total_pages INTEGER NOT NULL,
                    pending_pages INTEGER NOT NULL,
                    running_pages INTEGER NOT NULL DEFAULT 0,
                    completed_pages INTEGER NOT NULL DEFAULT 0,
                    failed_pages INTEGER NOT NULL DEFAULT 0,
                    cancellation_requested INTEGER NOT NULL DEFAULT 0,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    error_summary TEXT,
                    upload_path TEXT NOT NULL,
                    json_path TEXT,
                    markdown_path TEXT
                );
                CREATE TABLE IF NOT EXISTS pages (
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    page_number INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    available_at REAL NOT NULL DEFAULT 0,
                    lease_owner TEXT,
                    lease_expires REAL,
                    error TEXT,
                    result_path TEXT,
                    PRIMARY KEY (job_id, page_number)
                );
                CREATE INDEX IF NOT EXISTS pages_claim_idx
                    ON pages(status, available_at, page_number);
                CREATE INDEX IF NOT EXISTS jobs_cleanup_idx
                    ON jobs(status, completed_at);
                """
            )

    def create_job(
        self,
        *,
        owner_id: str,
        filename: str,
        output_format: str,
        total_pages: int,
        upload_path: Path,
    ) -> dict[str, Any]:
        now = time.time()
        job_id = uuid.uuid4().hex
        job_dir = self.settings.jobs_dir / job_id
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute(
                "SELECT count(*) FROM jobs WHERE status IN ('queued','running')"
            ).fetchone()[0]
            if active >= self.settings.max_jobs:
                raise QueueFullError
            (job_dir / "pages").mkdir(parents=True)
            db.execute(
                """INSERT INTO jobs (
                    id, owner_id, filename, output_format, created_at, updated_at,
                    total_pages, pending_pages, upload_path, json_path, markdown_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    owner_id,
                    filename,
                    output_format,
                    now,
                    now,
                    total_pages,
                    total_pages,
                    str(upload_path),
                    str(job_dir / "result.json"),
                    str(job_dir / "result.md"),
                ),
            )
            db.executemany(
                "INSERT INTO pages(job_id, page_number) VALUES (?, ?)",
                ((job_id, page) for page in range(1, total_pages + 1)),
            )
        return self.get(job_id, owner_id)  # type: ignore[return-value]

    def get(self, job_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
        with self.connect() as db:
            if owner_id is None:
                row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            else:
                row = db.execute(
                    "SELECT * FROM jobs WHERE id=? AND owner_id=?", (job_id, owner_id)
                ).fetchone()
        return _job_dict(row) if row else None

    def cancel(self, job_id: str, owner_id: str) -> dict[str, Any] | None:
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT status FROM jobs WHERE id=? AND owner_id=?", (job_id, owner_id)
            ).fetchone()
            if not row:
                return None
            if row["status"] not in TERMINAL:
                db.execute(
                    "UPDATE jobs SET cancellation_requested=1, updated_at=? WHERE id=?",
                    (now, job_id),
                )
                db.execute(
                    "UPDATE pages SET status='cancelled' WHERE job_id=? AND status='pending'",
                    (job_id,),
                )
                self._sync(db, job_id, now)
        return self.get(job_id, owner_id)

    def claim(self, worker_id: str) -> dict[str, Any] | None:
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            expired = db.execute(
                """SELECT p.job_id, p.page_number, p.attempts,
                          j.cancellation_requested
                   FROM pages p JOIN jobs j ON j.id=p.job_id
                   WHERE p.status='running' AND p.lease_expires < ?""",
                (now,),
            ).fetchall()
            touched: set[str] = set()
            for page in expired:
                status = "cancelled" if page["cancellation_requested"] else (
                    "pending" if page["attempts"] <= self.settings.max_retries else "failed"
                )
                db.execute(
                    """UPDATE pages SET status=?, lease_owner=NULL, lease_expires=NULL,
                       available_at=?, error='worker lease expired'
                       WHERE job_id=? AND page_number=?""",
                    (status, now, page["job_id"], page["page_number"]),
                )
                touched.add(page["job_id"])
            for job_id in touched:
                self._sync(db, job_id, now)

            page = db.execute(
                """SELECT p.job_id, p.page_number, p.attempts, j.upload_path
                   FROM pages p JOIN jobs j ON j.id=p.job_id
                   WHERE p.status='pending' AND p.available_at <= ?
                     AND j.status IN ('queued','running')
                     AND j.cancellation_requested=0
                     AND (SELECT count(*) FROM pages r
                          WHERE r.job_id=p.job_id AND r.status='running') < 2
                   ORDER BY COALESCE(j.last_claimed_at, 0), j.created_at, p.page_number
                   LIMIT 1""",
                (now,),
            ).fetchone()
            if not page:
                return None
            expires = now + self.settings.lease_seconds
            changed = db.execute(
                """UPDATE pages SET status='running', attempts=attempts+1,
                   lease_owner=?, lease_expires=?
                   WHERE job_id=? AND page_number=? AND status='pending'""",
                (worker_id, expires, page["job_id"], page["page_number"]),
            ).rowcount
            if not changed:
                return None
            db.execute(
                "UPDATE jobs SET last_claimed_at=?, status='running', updated_at=? WHERE id=?",
                (now, now, page["job_id"]),
            )
            self._sync(db, page["job_id"], now)
            return {
                "job_id": page["job_id"],
                "page_number": page["page_number"],
                "attempts": page["attempts"] + 1,
                "upload_path": page["upload_path"],
                "lease_expires": expires,
            }

    def finish_page(self, task: dict[str, Any], result_path: Path) -> dict[str, Any]:
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """UPDATE pages SET status='completed', result_path=?, error=NULL,
                   lease_owner=NULL, lease_expires=NULL
                   WHERE job_id=? AND page_number=? AND status='running'""",
                (str(result_path), task["job_id"], task["page_number"]),
            )
            self._sync(db, task["job_id"], now)
        return self.get(task["job_id"])  # type: ignore[return-value]

    def fail_page(self, task: dict[str, Any], error_message: str, transient: bool) -> None:
        now = time.time()
        retry = transient and task["attempts"] <= self.settings.max_retries
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """UPDATE pages SET status=?, available_at=?, error=?,
                   lease_owner=NULL, lease_expires=NULL
                   WHERE job_id=? AND page_number=? AND status='running'""",
                (
                    "pending" if retry else "failed",
                    now + min(30, 2 ** max(0, task["attempts"] - 1)) if retry else now,
                    error_message[:2000],
                    task["job_id"],
                    task["page_number"],
                ),
            )
            db.execute(
                """UPDATE jobs SET retry_count=retry_count+?, error_summary=?, updated_at=?
                   WHERE id=?""",
                (int(retry), error_message[:2000], now, task["job_id"]),
            )
            self._sync(db, task["job_id"], now)

    def claim_assembly(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                """UPDATE jobs SET status='assembling', completed_at=NULL, updated_at=?
                   WHERE id=? AND status='completed'""",
                (time.time(), job_id),
            ).rowcount
            if not changed:
                return None
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            return _job_dict(row)

    def complete_assembly(self, job_id: str) -> None:
        now = time.time()
        with self.connect() as db:
            db.execute(
                """UPDATE jobs SET status='completed', completed_at=?, updated_at=?,
                   error_summary=NULL WHERE id=? AND status='assembling'""",
                (now, now, job_id),
            )

    def fail_assembly(self, job_id: str, error_message: str) -> None:
        now = time.time()
        with self.connect() as db:
            db.execute(
                """UPDATE jobs SET status='failed', completed_at=?, updated_at=?,
                   error_summary=? WHERE id=? AND status='assembling'""",
                (now, now, error_message[:2000], job_id),
            )

    def cleanup(self) -> int:
        cutoff = time.time() - self.settings.retention_hours * 3600
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT id, upload_path FROM jobs WHERE status IN ('completed','failed','cancelled') "
                "AND completed_at < ?",
                (cutoff,),
            ).fetchall()
            for row in rows:
                Path(row["upload_path"]).unlink(missing_ok=True)
                shutil.rmtree(self.settings.jobs_dir / row["id"], ignore_errors=True)
                db.execute("DELETE FROM jobs WHERE id=?", (row["id"],))
        return len(rows)

    def _sync(self, db: sqlite3.Connection, job_id: str, now: float) -> None:
        counts = {
            row["status"]: row["count"]
            for row in db.execute(
                "SELECT status, count(*) AS count FROM pages WHERE job_id=? GROUP BY status",
                (job_id,),
            )
        }
        job = db.execute(
            "SELECT cancellation_requested FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        pending = counts.get("pending", 0)
        running = counts.get("running", 0)
        completed = counts.get("completed", 0)
        failed = counts.get("failed", 0)
        if not pending and not running:
            status = "cancelled" if job[0] else "failed" if failed else "completed"
            completed_at: float | None = now
        else:
            status = "running" if running or completed else "queued"
            completed_at = None
        db.execute(
            """UPDATE jobs SET status=?, pending_pages=?, running_pages=?,
               completed_pages=?, failed_pages=?, updated_at=?, completed_at=? WHERE id=?""",
            (status, pending, running, completed, failed, now, completed_at, job_id),
        )


def _job_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["cancellation_requested"] = bool(result["cancellation_requested"])
    return result
