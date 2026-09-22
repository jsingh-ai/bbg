from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from app.services import dashboard_service


class DashboardHistoryQueryTests(unittest.TestCase):
    def test_numeric_history_scan_uses_only_covering_table_and_bounded_range(self) -> None:
        start = datetime(2026, 9, 22, 8, 0, 0)
        end = start + timedelta(hours=1)

        with patch.object(dashboard_service.pool, "fetch_all", return_value=[]) as fetch_all:
            rows = dashboard_service._numeric_history_rows([11, 22], start, end, 6)

        self.assertEqual(rows, [])
        sql, params = fetch_all.call_args.args
        normalized_sql = " ".join(sql.split())
        self.assertIn("FROM opc_tag_values v", normalized_sql)
        self.assertNotIn("JOIN opc_tags", normalized_sql)
        self.assertNotIn("JOIN opc_tag_display_config", normalized_sql)
        self.assertIn("v.tag_id IN (%s,%s)", normalized_sql)
        self.assertIn("v.value_kind = 1", normalized_sql)
        self.assertIn("v.created_at >= %s", normalized_sql)
        self.assertIn("v.created_at <= %s", normalized_sql)
        self.assertEqual(params, (6, 6, 11, 22, start, end))

    def test_bucket_size_caps_each_series_for_long_ranges(self) -> None:
        start = datetime(2026, 8, 22, 0, 0, 0)
        end = start + timedelta(days=31)

        bucket_seconds = dashboard_service._history_bucket_seconds(start, end)

        self.assertEqual(bucket_seconds, 4464)
        self.assertLessEqual(((end - start).total_seconds() / bucket_seconds), 600)

    def test_history_response_includes_node_id(self) -> None:
        start = datetime(2026, 9, 22, 8, 0, 0)
        end = start + timedelta(hours=1)
        metadata = [{
            "tag_id": 11,
            "section_key": "020 - unwinder",
            "display_name": "Film tension",
            "browse_name": "filmTension",
            "node_id": "ns=6;s=::GlobalPV:filmTension",
        }]
        history = [{"tag_id": 11, "bucket_time": start, "value_num": 12.5}]

        with (
            patch.object(dashboard_service, "_filter_numeric_tag_ids", return_value=[11]),
            patch.object(dashboard_service.pool, "fetch_all", return_value=metadata),
            patch.object(dashboard_service, "_numeric_history_rows", return_value=history),
        ):
            result = dashboard_service.get_history(1, "020 - unwinder", start, end, [11])

        self.assertEqual(result["series"][0]["node_id"], "ns=6;s=::GlobalPV:filmTension")
        self.assertEqual(result["series"][0]["points"], [[start.isoformat(), 12.5]])

    def test_section_history_scans_only_metadata_approved_tags(self) -> None:
        start = datetime(2026, 9, 22, 8, 0, 0)
        end = start + timedelta(hours=1)
        metadata = [{
            "tag_id": 11,
            "section_key": "020 - unwinder",
            "display_name": "Film tension",
            "browse_name": "filmTension",
            "node_id": "node-11",
        }]

        with (
            patch.object(dashboard_service, "_filter_numeric_tag_ids", return_value=[11, 22]),
            patch.object(dashboard_service.pool, "fetch_all", return_value=metadata),
            patch.object(dashboard_service, "_numeric_history_rows", return_value=[]) as history_rows,
        ):
            result = dashboard_service.get_history(1, "020 - unwinder", start, end, [11, 22])

        history_rows.assert_called_once_with([11], start, end, 6)
        self.assertEqual([series["tag_id"] for series in result["series"]], [11])


if __name__ == "__main__":
    unittest.main()
