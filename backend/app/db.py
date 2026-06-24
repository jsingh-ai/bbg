from __future__ import annotations

import queue
import threading
from contextlib import contextmanager
from typing import Any, Iterator

import pymysql
from pymysql.connections import Connection
from pymysql.cursors import DictCursor

from .config import get_settings


class MySQLPool:
    """Small thread-safe PyMySQL connection pool for predictable raw SQL access."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._pool: queue.Queue[Connection] = queue.Queue(maxsize=self.settings.db_pool_size)
        self._lock = threading.Lock()
        self._created = 0

    def _connect(self) -> Connection:
        return pymysql.connect(
            host=self.settings.db_host,
            port=self.settings.db_port,
            user=self.settings.db_user,
            password=self.settings.db_password,
            database=self.settings.db_name,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
            connect_timeout=self.settings.db_connect_timeout,
            read_timeout=60,
            write_timeout=60,
        )

    def _get(self) -> Connection:
        try:
            conn = self._pool.get_nowait()
        except queue.Empty:
            with self._lock:
                if self._created < self.settings.db_pool_size:
                    self._created += 1
                    return self._connect()
            conn = self._pool.get()

        try:
            conn.ping(reconnect=True)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            conn = self._connect()
        return conn

    def _put(self, conn: Connection) -> None:
        try:
            self._pool.put_nowait(conn)
        except queue.Full:
            try:
                conn.close()
            except Exception:
                pass

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        conn = self._get()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put(conn)

    def fetch_all(self, sql: str, params: tuple[Any, ...] | dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())

    def fetch_one(self, sql: str, params: tuple[Any, ...] | dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return dict(row) if row else None

    def execute(self, sql: str, params: tuple[Any, ...] | dict[str, Any] | None = None) -> int:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return int(cur.rowcount)

    def execute_many(self, sql: str, params: list[tuple[Any, ...]] | list[dict[str, Any]]) -> int:
        if not params:
            return 0
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, params)
                return int(cur.rowcount)


pool = MySQLPool()
