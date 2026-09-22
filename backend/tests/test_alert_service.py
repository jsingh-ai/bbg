from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from app.services import alert_service


class AlertServiceTests(unittest.TestCase):
    def test_alert_listing_includes_node_id(self) -> None:
        rows = [{"alert_id": 1, "tag_id": 12, "node_id": "ns=6;s=pressure"}]

        with patch.object(alert_service.pool, "fetch_all", return_value=rows) as fetch_all:
            result = alert_service.list_alerts(1, active_only=False)

        self.assertEqual(result[0]["node_id"], "ns=6;s=pressure")
        sql = " ".join(fetch_all.call_args.args[0].split())
        self.assertIn("LEFT JOIN opc_tags t", sql)
        self.assertIn("t.node_id", sql)

    def test_stale_latest_value_does_not_create_alert(self) -> None:
        limit_row = {
            "recipe_id": 7,
            "machine_id": 1,
            "tag_id": 12,
            "section_key": "020 - unwinder",
            "min_value": 10.0,
            "max_value": 20.0,
            "display_name": "Pressure",
            "browse_name": None,
            "node_id": "pressure",
            "captured_at": datetime.now() - timedelta(minutes=30),
            "is_good": 1,
            "error_text": None,
            "value_kind": 1,
            "value_num": 100.0,
        }

        with (
            patch.object(alert_service, "get_active_recipe", return_value={"recipe_id": 7}),
            patch.object(alert_service, "get_settings", return_value=SimpleNamespace(alert_max_data_age_seconds=300)),
            patch.object(alert_service.pool, "fetch_all", side_effect=[[limit_row], []]),
            patch.object(alert_service.pool, "execute") as execute,
        ):
            result = alert_service.evaluate_alerts(1)

        self.assertTrue(result["evaluated"])
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["skipped_stale_or_bad"], 1)
        execute.assert_not_called()

    def test_removed_limit_marks_current_alert_returned(self) -> None:
        open_alert = {"alert_id": 99, "tag_id": 12, "is_currently_out_of_range": 1}

        with (
            patch.object(alert_service, "get_active_recipe", return_value={"recipe_id": 7}),
            patch.object(alert_service, "get_settings", return_value=SimpleNamespace(alert_max_data_age_seconds=300)),
            patch.object(alert_service.pool, "fetch_all", side_effect=[[], [open_alert]]),
            patch.object(alert_service.pool, "execute", return_value=1) as execute,
        ):
            result = alert_service.evaluate_alerts(1)

        self.assertEqual(result["returned"], 1)
        self.assertIn("returned_to_range_at", execute.call_args.args[0])
        self.assertEqual(execute.call_args.args[1], (99,))


if __name__ == "__main__":
    unittest.main()
