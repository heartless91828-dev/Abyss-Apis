from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

DB_URL = os.getenv("DATABASE_URL", "").strip()
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
SQLITE_PATH = os.getenv("USAGE_DB_PATH", os.path.join(DATA_DIR, "usage.sqlite3"))

_sqlite_init_lock = threading.Lock()


def ist_now() -> datetime:
    return datetime.now(IST)


def _buckets(now: datetime | None = None) -> tuple[str, str]:
    now = now or ist_now()
    return now.strftime("%Y%m%d%H"), now.strftime("%Y%m%d")


def _is_postgres() -> bool:
    return DB_URL.startswith(("postgres://", "postgresql://", "postgresql+psycopg://"))


class UsageStore:
    def __init__(self) -> None:
        self.postgres = _is_postgres()
        if self.postgres:
            try:
                import psycopg
                self.psycopg = psycopg
            except ImportError as exc:
                raise RuntimeError("DATABASE_URL is set but psycopg is not installed") from exc
        else:
            os.makedirs(os.path.dirname(SQLITE_PATH) or ".", exist_ok=True)
        self.init_db()

    @contextmanager
    def _sqlite(self):
        conn = sqlite3.connect(SQLITE_PATH, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self) -> None:
        if self.postgres:
            with self.psycopg.connect(DB_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS api_usage (
                            api_key TEXT PRIMARY KEY,
                            used_total BIGINT NOT NULL DEFAULT 0,
                            hour_bucket TEXT NOT NULL DEFAULT '',
                            hour_used BIGINT NOT NULL DEFAULT 0,
                            day_bucket TEXT NOT NULL DEFAULT '',
                            day_used BIGINT NOT NULL DEFAULT 0,
                            inflight BIGINT NOT NULL DEFAULT 0,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                    """)
                conn.commit()
        else:
            with _sqlite_init_lock, self._sqlite() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS api_usage (
                        api_key TEXT PRIMARY KEY,
                        used_total INTEGER NOT NULL DEFAULT 0,
                        hour_bucket TEXT NOT NULL DEFAULT '',
                        hour_used INTEGER NOT NULL DEFAULT 0,
                        day_bucket TEXT NOT NULL DEFAULT '',
                        day_used INTEGER NOT NULL DEFAULT 0,
                        inflight INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL DEFAULT ''
                    )
                """)

    @staticmethod
    def _reset_buckets(row, hour_bucket: str, day_bucket: str):
        hour_used = row["hour_used"]
        day_used = row["day_used"]
        if row["hour_bucket"] != hour_bucket:
            hour_used = 0
        if row["day_bucket"] != day_bucket:
            day_used = 0
        return int(hour_used), int(day_used)

    def reserve(self, api_key: str, limit_per_hour, limit_per_day) -> tuple[bool, str, int]:
        """Atomically admit one request without serializing requests for the same key."""
        hour_bucket, day_bucket = _buckets()
        now = ist_now()

        if self.postgres:
            with self.psycopg.connect(DB_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT * FROM api_usage WHERE api_key=%s FOR UPDATE",
                        (api_key,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        cur.execute(
                            "INSERT INTO api_usage(api_key,hour_bucket,day_bucket,updated_at) VALUES(%s,%s,%s,NOW())",
                            (api_key, hour_bucket, day_bucket),
                        )
                        cur.execute("SELECT * FROM api_usage WHERE api_key=%s FOR UPDATE", (api_key,))
                        row = cur.fetchone()

                    cols = [d.name for d in cur.description]
                    row = dict(zip(cols, row))
                    hour_used, day_used = self._reset_buckets(row, hour_bucket, day_bucket)
                    inflight = int(row["inflight"])
                    total = int(row["used_total"])

                    if limit_per_hour is not None and hour_used + inflight >= int(limit_per_hour):
                        conn.rollback()
                        return False, "Hourly Limit Exceeded", total
                    if limit_per_day is not None and day_used + inflight >= int(limit_per_day):
                        conn.rollback()
                        return False, "Daily Limit Exceeded", total

                    cur.execute(
                        """
                        UPDATE api_usage
                        SET hour_bucket=%s, hour_used=%s, day_bucket=%s, day_used=%s,
                            inflight=inflight+1, updated_at=%s
                        WHERE api_key=%s
                        """,
                        (hour_bucket, hour_used, day_bucket, day_used, now, api_key),
                    )
                conn.commit()
                return True, "OK", total

        with self._sqlite() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM api_usage WHERE api_key=?", (api_key,)).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO api_usage(api_key,hour_bucket,day_bucket,updated_at) VALUES(?,?,?,?)",
                    (api_key, hour_bucket, day_bucket, now.isoformat()),
                )
                row = conn.execute("SELECT * FROM api_usage WHERE api_key=?", (api_key,)).fetchone()

            hour_used, day_used = self._reset_buckets(row, hour_bucket, day_bucket)
            inflight = int(row["inflight"])
            total = int(row["used_total"])

            if limit_per_hour is not None and hour_used + inflight >= int(limit_per_hour):
                conn.rollback()
                return False, "Hourly Limit Exceeded", total
            if limit_per_day is not None and day_used + inflight >= int(limit_per_day):
                conn.rollback()
                return False, "Daily Limit Exceeded", total

            conn.execute(
                """
                UPDATE api_usage
                SET hour_bucket=?, hour_used=?, day_bucket=?, day_used=?, inflight=inflight+1, updated_at=?
                WHERE api_key=?
                """,
                (hour_bucket, hour_used, day_bucket, day_used, now.isoformat(), api_key),
            )
            conn.commit()
            return True, "OK", total

    def finish(self, api_key: str, success: bool) -> int:
        hour_bucket, day_bucket = _buckets()
        now = ist_now()

        if self.postgres:
            with self.psycopg.connect(DB_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM api_usage WHERE api_key=%s FOR UPDATE", (api_key,))
                    row = cur.fetchone()
                    if row is None:
                        conn.rollback()
                        return 0
                    cols = [d.name for d in cur.description]
                    row = dict(zip(cols, row))
                    hour_used, day_used = self._reset_buckets(row, hour_bucket, day_bucket)
                    inflight = max(0, int(row["inflight"]) - 1)
                    total = int(row["used_total"])
                    if success:
                        hour_used += 1
                        day_used += 1
                        total += 1
                    cur.execute(
                        """
                        UPDATE api_usage
                        SET hour_bucket=%s, hour_used=%s, day_bucket=%s, day_used=%s,
                            inflight=%s, used_total=%s, updated_at=%s
                        WHERE api_key=%s
                        """,
                        (hour_bucket, hour_used, day_bucket, day_used, inflight, total, now, api_key),
                    )
                conn.commit()
                return total

        with self._sqlite() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM api_usage WHERE api_key=?", (api_key,)).fetchone()
            if row is None:
                conn.rollback()
                return 0
            hour_used, day_used = self._reset_buckets(row, hour_bucket, day_bucket)
            inflight = max(0, int(row["inflight"]) - 1)
            total = int(row["used_total"])
            if success:
                hour_used += 1
                day_used += 1
                total += 1
            conn.execute(
                """
                UPDATE api_usage
                SET hour_bucket=?, hour_used=?, day_bucket=?, day_used=?, inflight=?, used_total=?, updated_at=?
                WHERE api_key=?
                """,
                (hour_bucket, hour_used, day_bucket, day_used, inflight, total, now.isoformat(), api_key),
            )
            conn.commit()
            return total

    def get_total(self, api_key: str) -> int:
        if self.postgres:
            with self.psycopg.connect(DB_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT used_total FROM api_usage WHERE api_key=%s", (api_key,))
                    row = cur.fetchone()
                    return int(row[0]) if row else 0
        with self._sqlite() as conn:
            row = conn.execute("SELECT used_total FROM api_usage WHERE api_key=?", (api_key,)).fetchone()
            return int(row[0]) if row else 0
