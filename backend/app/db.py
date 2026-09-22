from __future__ import annotations

import queue
import threading
from contextlib import contextmanager
from typing import Any, Iterator

import pymysql
from pymysql import err as pymysql_err
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

    def _release_slot(self) -> None:
        with self._lock:
            self._created = max(0, self._created - 1)

    def _discard(self, conn: Connection) -> None:
        try:
            conn.close()
        except Exception:
            pass
        self._release_slot()

    def _create_if_available(self) -> Connection | None:
        with self._lock:
            if self._created >= self.settings.db_pool_size:
                return None
            self._created += 1
        try:
            return self._connect()
        except Exception:
            self._release_slot()
            raise

    def _get(self) -> Connection:
        try:
            conn = self._pool.get_nowait()
        except queue.Empty:
            conn = self._create_if_available()
            if conn is None:
                try:
                    conn = self._pool.get(timeout=max(self.settings.db_connect_timeout, 1))
                except queue.Empty as exc:
                    raise pymysql_err.OperationalError(
                        1040,
                        "Timed out waiting for an available MySQL connection",
                    ) from exc

        try:
            conn.ping(reconnect=True)
        except Exception:
            self._discard(conn)
            conn = self._create_if_available()
            if conn is None:
                raise pymysql_err.OperationalError(1040, "Unable to replace a failed MySQL connection")
        return conn

    def _put(self, conn: Connection) -> None:
        if not getattr(conn, "open", False):
            self._discard(conn)
            return
        try:
            self._pool.put_nowait(conn)
        except queue.Full:
            self._discard(conn)

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        conn = self._get()
        reusable = True
        try:
            yield conn
            conn.commit()
        except Exception as exc:
            if isinstance(exc, (pymysql_err.InterfaceError, pymysql_err.OperationalError)):
                reusable = False
            try:
                conn.rollback()
            except Exception:
                # Preserve the original query error. A failed rollback means the
                # connection is dead and must never be returned to the pool.
                reusable = False
            raise
        finally:
            if reusable:
                self._put(conn)
            else:
                self._discard(conn)

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
