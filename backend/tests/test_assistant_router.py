from __future__ import annotations

import unittest

from app.services.assistant_router import route_assistant_message
from app.services.assistant_service import _comparison_range_for_route, _deterministic_answer
from app.services.process_analysis import (
    _is_dependent_speed_context_row,
    _is_state_context_row,
    make_contextual_label,
    should_exclude_section,
)


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

    def test_plain_production_today_has_no_compare(self) -> None:
        route = route_assistant_message("How was production today?")
        self.assertIsNone(route["compare_to"])
        self.assertIsNone(_comparison_range_for_route(route, "How was production today?"))

    def test_production_answer_without_comparison_text(self) -> None:
        text = _deterministic_answer(
            "production_summary",
            {
                "range": {"label": "Today"},
                "good_bags": 1,
                "bad_bags": 2,
                "total_bags": 3,
                "bad_rate_pct": 66.67,
                "warnings": [],
                "total_counter_bags": 10,
            },
        )
        self.assertNotIn("yesterday", text.lower())

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

    def test_active_alarms(self) -> None:
        route = route_assistant_message("Show active alarms")
        self.assertEqual(route["intent"], "section_summary")
        self.assertEqual(route["resolved_system"], "alarm/system")
        self.assertIn("alarm system", route["section_terms"])

    def test_contextual_label_nozzle_flow_rate(self) -> None:
        label = make_contextual_label(
            {
                "opc_path": "Global PV/360 - bottom sealing/state/nozzle - 3/flow rate",
                "display_name": "flow rate",
            }
        )
        self.assertEqual(label, "nozzle - 3 / flow rate")

    def test_contextual_label_web_tension(self) -> None:
        label = make_contextual_label(
            {
                "opc_path": "Global PV/080 - dancer/state/web tension/currentPressure",
                "display_name": "currentPressure",
            }
        )
        self.assertEqual(label, "web tension / currentPressure")

    def test_state_tags_move_to_context_by_default(self) -> None:
        self.assertTrue(
            _is_state_context_row(
                {"display_name": "state", "opc_path": "Global PV/020 - unwinder/state/state", "label": "state"},
                message="What changed around the last stop?",
            )
        )

    def test_explicit_state_question_bypasses_state_context(self) -> None:
        self.assertFalse(
            _is_state_context_row(
                {"display_name": "state", "opc_path": "Global PV/020 - unwinder/state/state", "label": "state"},
                message="Show me state changes around the last stop",
            )
        )

    def test_dependent_speed_moves_to_context_by_default(self) -> None:
        self.assertTrue(
            _is_dependent_speed_context_row(
                {
                    "display_name": "current speed",
                    "opc_path": "Global PV/265 - hotmelt - bottom forming/state/nozzle - a-side/current speed",
                    "label": "nozzle - a-side / current speed",
                },
                message="What changed the most in the last hour?",
            )
        )

    def test_explicit_speed_question_bypasses_dependent_speed_context(self) -> None:
        self.assertFalse(
            _is_dependent_speed_context_row(
                {
                    "display_name": "cycle performance",
                    "opc_path": "Global PV/020 - unwinder/state/cycle performance",
                    "label": "cycle performance",
                },
                message="Show me speed changes around the last stop",
            )
        )

    def test_exclude_exact_i_section(self) -> None:
        self.assertTrue(should_exclude_section("i", ["i"]))

    def test_do_not_exclude_unwinder_for_i_term(self) -> None:
        self.assertFalse(should_exclude_section("020 - unwinder", ["i"]))

    def test_do_not_exclude_storage_cylinder_for_i_term(self) -> None:
        self.assertFalse(should_exclude_section("290 - storage cylinder", ["i"]))

    def test_do_not_exclude_bottom_sealing_for_i_term(self) -> None:
        self.assertFalse(should_exclude_section("360 - bottom sealing", ["i"]))

    def test_do_not_exclude_general_i16_for_i_term(self) -> None:
        self.assertFalse(should_exclude_section("A00-I16 - general", ["i"]))


if __name__ == "__main__":
    unittest.main()
