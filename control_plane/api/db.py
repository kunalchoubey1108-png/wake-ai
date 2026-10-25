from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

_lock = threading.Lock()


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY,
                  ip TEXT,
                  status TEXT,
                  repo_label TEXT,
                  created_at REAL,
                  updated_at REAL,
                  result_json TEXT,
                  work_dir TEXT,
                  replay INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS rate (
                  ip TEXT,
                  ts REAL
                );
                """
            )

    def insert_job(self, job_id: str, ip: str, repo_label: str, work_dir: str, replay: bool = False) -> None:
        now = time.time()
        with _lock, self._conn() as c:
            c.execute(
                "INSERT INTO jobs(id,ip,status,repo_label,created_at,updated_at,result_json,work_dir,replay) VALUES(?,?,?,?,?,?,?,?,?)",
                (job_id, ip, "queued", repo_label, now, now, "{}", work_dir, 1 if replay else 0),
            )

    def update_job(self, job_id: str, status: str, result: dict[str, Any] | None = None) -> None:
        with _lock, self._conn() as c:
            if result is not None:
                c.execute(
                    "UPDATE jobs SET status=?, updated_at=?, result_json=? WHERE id=?",
                    (status, time.time(), json.dumps(result), job_id),
                )
            else:
                c.execute("UPDATE jobs SET status=?, updated_at=? WHERE id=?", (status, time.time(), job_id))

    def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["result"] = json.loads(d.pop("result_json") or "{}")
        return d

    def count_recent(self, ip: str, window_sec: float = 3600) -> int:
        since = time.time() - window_sec
        with self._conn() as c:
            n = c.execute("SELECT COUNT(*) FROM rate WHERE ip=? AND ts>?", (ip, since)).fetchone()[0]
        return int(n)

    def record_rate(self, ip: str) -> None:
        with _lock, self._conn() as c:
            c.execute("INSERT INTO rate(ip,ts) VALUES(?,?)", (ip, time.time()))

    def count_running(self, ip: str) -> int:
        with self._conn() as c:
            n = c.execute("SELECT COUNT(*) FROM jobs WHERE ip=? AND status='running'", (ip,)).fetchone()[0]
        return int(n)
