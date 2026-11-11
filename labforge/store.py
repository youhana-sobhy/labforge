"""SQLite store for lab records and the activity log (also the source for usage KPIs)."""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS labs (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  template TEXT NOT NULL,
  owner TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at REAL NOT NULL,
  ready_at REAL,
  expires_at REAL NOT NULL,
  destroyed_at REAL,
  node_count INTEGER NOT NULL,
  error TEXT,
  topology TEXT NOT NULL,
  runtime TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lab_id TEXT,
  ts REAL NOT NULL,
  level TEXT NOT NULL,
  message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS check_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lab_id TEXT NOT NULL,
  ts REAL NOT NULL,
  passed INTEGER NOT NULL,
  total INTEGER NOT NULL,
  results TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_lab ON events(lab_id, id);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

ACTIVE = ("deploying", "running", "destroying")


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)
        rows = self._q("SELECT value FROM meta WHERE key='instance'")
        if rows:
            self.instance_id = rows[0]["value"]
        else:
            self.instance_id = secrets.token_hex(4)
            self._q("INSERT INTO meta (key, value) VALUES ('instance', ?)", (self.instance_id,))

    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    # ---- labs -------------------------------------------------------------------------------------------
    def create_lab(self, rec: dict) -> None:
        cols = ",".join(rec)
        self._q(f"INSERT INTO labs ({cols}) VALUES ({','.join('?' * len(rec))})", tuple(rec.values()))

    def update_lab(self, lab_id: str, **fields) -> None:
        if not fields:
            return
        sets = ",".join(f"{k}=?" for k in fields)
        self._q(f"UPDATE labs SET {sets} WHERE id=?", (*fields.values(), lab_id))

    def get_lab(self, lab_id: str) -> dict | None:
        rows = self._q("SELECT * FROM labs WHERE id=?", (lab_id,))
        return _lab(rows[0]) if rows else None

    def list_labs(self, active_only: bool = False, limit: int = 200) -> list[dict]:
        if active_only:
            rows = self._q(
                f"SELECT * FROM labs WHERE status IN ({','.join('?' * len(ACTIVE))}) ORDER BY created_at DESC",
                ACTIVE,
            )
        else:
            rows = self._q("SELECT * FROM labs ORDER BY created_at DESC LIMIT ?", (limit,))
        return [_lab(r) for r in rows]

    # ---- events -----------------------------------------------------------------------------------------
    def log(self, lab_id: str | None, message: str, level: str = "info") -> None:
        self._q("INSERT INTO events (lab_id, ts, level, message) VALUES (?,?,?,?)",
                (lab_id, time.time(), level, message))

    def events(self, lab_id: str | None = None, after: int = 0, limit: int = 200) -> list[dict]:
        if lab_id:
            rows = self._q("SELECT * FROM events WHERE lab_id=? AND id>? ORDER BY id DESC LIMIT ?",
                           (lab_id, after, limit))
        else:
            rows = self._q("SELECT e.*, l.name AS lab_name FROM events e LEFT JOIN labs l ON l.id=e.lab_id "
                           "WHERE e.id>? ORDER BY e.id DESC LIMIT ?", (after, limit))
        return [dict(r) for r in reversed(rows)]

    # ---- checks -----------------------------------------------------------------------------------------
    def save_check_run(self, lab_id: str, results: list[dict]) -> dict:
        passed = sum(1 for r in results if r["ok"])
        ts = time.time()
        self._q("INSERT INTO check_runs (lab_id, ts, passed, total, results) VALUES (?,?,?,?,?)",
                (lab_id, ts, passed, len(results), json.dumps(results)))
        return {"ts": ts, "passed": passed, "total": len(results), "results": results}

    def last_check_run(self, lab_id: str) -> dict | None:
        rows = self._q("SELECT * FROM check_runs WHERE lab_id=? ORDER BY id DESC LIMIT 1", (lab_id,))
        if not rows:
            return None
        r = rows[0]
        return {"ts": r["ts"], "passed": r["passed"], "total": r["total"], "results": json.loads(r["results"])}

    # ---- KPIs -------------------------------------------------------------------------------------------
    def stats(self, now: float | None = None) -> dict:
        now = now or time.time()
        since = now - 30 * 86400
        labs = self._q("SELECT * FROM labs WHERE created_at>=?", (since,))
        device_hours = 0.0
        deploy_times = []
        for r in labs:
            start = r["ready_at"] or r["created_at"]
            end = r["destroyed_at"] or (now if r["status"] in ACTIVE else start)
            device_hours += max(0.0, end - start) / 3600 * r["node_count"]
            if r["ready_at"]:
                deploy_times.append(r["ready_at"] - r["created_at"])
        runs = self._q("SELECT passed, total FROM check_runs WHERE ts>=?", (since,))
        checks_total = sum(r["total"] for r in runs)
        checks_passed = sum(r["passed"] for r in runs)
        by_template: dict[str, int] = {}
        for r in labs:
            by_template[r["template"]] = by_template.get(r["template"], 0) + 1
        owners = {r["owner"] for r in labs}
        daily = []
        for d in range(13, -1, -1):
            day_start = _day_start(now) - d * 86400
            daily.append({
                "day": time.strftime("%Y-%m-%d", time.localtime(day_start)),
                "labs": sum(1 for r in labs if day_start <= r["created_at"] < day_start + 86400),
            })
        return {
            "active_labs": sum(1 for r in labs if r["status"] in ACTIVE),
            "labs_launched_30d": len(labs),
            "engineers_30d": len(owners),
            "device_hours_30d": round(device_hours, 1),
            "avg_deploy_seconds": round(sum(deploy_times) / len(deploy_times), 1) if deploy_times else None,
            "auto_expired_30d": sum(1 for r in labs if r["status"] == "expired"),
            "check_runs_30d": len(runs),
            "checks_total_30d": checks_total,
            "check_pass_rate": round(100 * checks_passed / checks_total, 1) if checks_total else None,
            "by_template": by_template,
            "daily": daily,
        }


def _day_start(ts: float) -> float:
    lt = time.localtime(ts)
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def _lab(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["topology"] = json.loads(d["topology"])
    d["runtime"] = json.loads(d["runtime"] or "{}")
    return d
