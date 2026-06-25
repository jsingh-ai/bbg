from __future__ import annotations

import unittest

from app.services.assistant_router import route_assistant_message


class AssistantRouterTests(unittest.TestCase):
    def test_production_today(self) -> None:
        route = route_assistant_message("How was production today?")
        self.assertEqual(route["intent"], "production_summary")
        self.assertEqual(route["time_range"], "today")

    def test_compare_today_to_yesterday(self) -> None:
        route = route_assistant_message("Compare today to yesterday")
        self.assertEqual(route["intent"], "production_summary")
        self.assertEqual(route["time_range"], "today")
        self.assertEqual(route["compare_to"], "yesterday")

    def test_stop_summary(self) -> None:
        route = route_assistant_message("How many stops in the last 24 hours?")
        self.assertEqual(route["intent"], "stop_summary")
        self.assertEqual(route["time_range"], "last_24_hours")

    def test_most_changed(self) -> None:
        route = route_assistant_message("What changed the most in the last hour?")
        self.assertEqual(route["intent"], "most_changed_parameters")
        self.assertEqual(route["time_range"], "last_hour")
        self.assertFalse(route["section_terms"])
        self.assertNotEqual(route["intent"], "production_summary")

    def test_values_around_last_stop(self) -> None:
        route = route_assistant_message("What changed around the last stop?")
        self.assertEqual(route["intent"], "values_around_last_stop")
        self.assertNotEqual(route["intent"], "stop_summary")

    def test_unwinder_section(self) -> None:
        route = route_assistant_message("What happened in the unwinder today?")
        self.assertEqual(route["intent"], "section_summary")
        self.assertEqual(route["resolved_system"], "unwinder")
        self.assertIn("unwinder", route["section_terms"])
        self.assertNotIn("i", route["section_terms"])
        self.assertNotEqual(route["intent"], "production_summary")

    def test_dancer_section(self) -> None:
        route = route_assistant_message("What happened in the dancer today?")
        self.assertEqual(route["intent"], "section_summary")
        self.assertEqual(route["resolved_system"], "dancer")
        self.assertIn("dancer", route["section_terms"])

    def test_plc_temperatures(self) -> None:
        route = route_assistant_message("Show PLC temperatures")
        self.assertIn(route["intent"], {"section_summary", "most_changed_parameters"})
        self.assertEqual(route["resolved_system"], "plc/io/system")
        self.assertIn("i", route["section_terms"])


if __name__ == "__main__":
    unittest.main()
