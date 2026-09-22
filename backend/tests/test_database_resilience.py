from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pymysql import err as pymysql_err

from app.db import MySQLPool
from app.services import dashboard_service


class _BrokenConnection:
    open = True

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        raise pymysql_err.InterfaceError(0, "")

    def close(self) -> None:
        self.open = False


class DatabasePoolResilienceTests(unittest.TestCase):
    def test_failed_rollback_does_not_mask_original_query_error(self) -> None:
        db_pool = MySQLPool()
        conn = _BrokenConnection()
        db_pool._get = Mock(return_value=conn)
        db_pool._put = Mock()
        db_pool._discard = Mock()

        original = pymysql_err.OperationalError(2013, "Lost connection during query")
        with self.assertRaises(pymysql_err.OperationalError) as raised:
            with db_pool.connection():
                raise original

        self.assertIs(raised.exception, original)
        db_pool._discard.assert_called_once_with(conn)
        db_pool._put.assert_not_called()

    def test_failed_initial_connect_releases_reserved_pool_slot(self) -> None:
        db_pool = MySQLPool()
        db_pool.settings = SimpleNamespace(db_pool_size=1, db_connect_timeout=1)
        db_pool._connect = Mock(side_effect=pymysql_err.OperationalError(2003, "connect failed"))

        with self.assertRaises(pymysql_err.OperationalError):
            db_pool._get()

        self.assertEqual(db_pool._created, 0)


class DashboardSummaryResilienceTests(unittest.TestCase):
    def test_history_timeout_keeps_live_summary_available(self) -> None:
        tag_row = {
            "tag_id": 10,
            "opc_path": dashboard_service.SPEED_PATH,
            "display_name": "Machine speed",
            "browse_name": None,
            "node_id": "speed",
            "value_kind": 1,
            "value_num": 25.0,
            "value_bool": None,
            "value_text": None,
            "error_text": None,
        }
        timeout = pymysql_err.OperationalError(2013, "Lost connection during query (timed out)")

        with patch.object(dashboard_service.pool, "fetch_all", side_effect=[[tag_row], timeout, timeout]):
            summary = dashboard_service.get_dashboard_summary(1)

        self.assertEqual(summary["speed"]["current_value"], "25")
        self.assertEqual(summary["speed"]["points"], [])
        self.assertFalse(summary["uptime"]["available"])
        self.assertEqual(len(summary["warnings"]), 2)


if __name__ == "__main__":
    unittest.main()
