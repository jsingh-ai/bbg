from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.services import process_analysis
from app.services.assistant_router import route_assistant_message
from app.services.assistant_service import _build_openai_messages, _comparison_range_for_route, _deterministic_answer, _top_labels
from app.services.assistant_intents import has_explicit_plc_context
from app.services.process_analysis import (
    _filter_process_row,
    _is_dependent_speed_context_row,
    _is_dependent_speed_row,
    _is_explicit_alarm_context_request,
    _is_explicit_counter_context_request,
    _is_explicit_plc_context_request,
    _is_explicit_speed_context_request,
    _is_explicit_state_context_request,
    _is_machine_speed_context_row,
    _is_state_context_row,
    _production_warnings,
    _rank_visible_around_stop_rows,
    dedupe_rows,
    make_contextual_label,
    should_exclude_section,
)


class AssistantRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_process_settings = process_analysis._settings
        process_analysis._settings = lambda: SimpleNamespace(
            assistant_state_context_enabled=True,
            assistant_speed_context_enabled=True,
            assistant_dependent_speed_term_list=["current speed", "cycle performance"],
            assistant_excluded_state_term_list=["state", "status", "mode"],
            assistant_excluded_section_key_list=["i", "alarm system"],
            assistant_excluded_path_contains_list=["/i/o/", "alarm system"],
            assistant_excluded_tag_term_list=[
                "counter",
                "count",
                "number of",
                "good",
                "bad",
                "total",
                "shift",
                "job",
                "active alarms",
                "max severity",
                "storagewear",
            ],
        )

    def tearDown(self) -> None:
        process_analysis._settings = self.original_process_settings

    def test_production_today(self) -> None:
        route = route_assistant_message("How was production today?")
        self.assertEqual(route["intent"], "production_summary")
        self.assertEqual(route["time_range"], "today")
        self.assertFalse(route["explicit_plc_context"])

    def test_compare_today_to_yesterday(self) -> None:
        route = route_assistant_message("Compare today to yesterday")
        self.assertEqual(route["intent"], "production_summary")
        self.assertEqual(route["time_range"], "today")
        self.assertEqual(route["compare_to"], "yesterday")

    def test_compare_speed_does_not_route_to_production(self) -> None:
        route = route_assistant_message("Compare speed this week")
        self.assertNotEqual(route["intent"], "production_summary")
        self.assertEqual(route["time_range"], "last_week")

    def test_compare_stops_does_not_route_to_production(self) -> None:
        route = route_assistant_message("Compare stops this week")
        self.assertNotEqual(route["intent"], "production_summary")
        self.assertEqual(route["matched_rule"], "compare_stops_not_implemented")

    def test_compare_unwinder_does_not_route_to_production(self) -> None:
        route = route_assistant_message("Compare unwinder today to yesterday")
        self.assertEqual(route["intent"], "section_summary")
        self.assertEqual(route["time_range"], "today")
        self.assertEqual(route["compare_to"], "yesterday")
        self.assertEqual(route["resolved_system"], "unwinder")

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

    def test_openai_prompt_builder_limits_model_to_supplied_json(self) -> None:
        messages = _build_openai_messages("What changed?", "most_changed_parameters", {"parameters": []})
        system_prompt = messages[0]["content"].lower()
        self.assertIn("only use supplied json", system_prompt)
        self.assertIn("do not claim causation", system_prompt)

    def test_openai_prompt_sanitized_payload_omits_paths_by_default(self) -> None:
        messages = _build_openai_messages(
            "What happened in the unwinder?",
            "section_summary",
            {
                "error": {
                    "code": "missing_tag",
                    "message": "missing",
                    "configured_path": "Global PV/secret/path",
                },
                "route": {"intent": "section_summary", "time_range": "today"},
            },
            cards=[],
            tables=[
                {
                    "title": "Matching Tags",
                    "columns": ["Label", "OPC Path"],
                    "rows": [["current diameter", "Global PV/020 - unwinder/state/current diameter"]],
                }
            ],
        )
        user_prompt = messages[1]["content"]
        self.assertIn("current diameter", user_prompt)
        self.assertNotIn("Global PV/secret/path", user_prompt)
        self.assertNotIn("Global PV/020 - unwinder/state/current diameter", user_prompt)

    def test_openai_prompt_can_send_raw_when_explicitly_enabled(self) -> None:
        messages = _build_openai_messages(
            "What happened in the unwinder?",
            "section_summary",
            {"matching_tags": [{"opc_path": "Global PV/020 - unwinder/state/current diameter"}]},
            send_raw=True,
        )
        self.assertIn("Global PV/020 - unwinder/state/current diameter", messages[1]["content"])

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
        self.assertFalse(route["explicit_speed_context"])

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
                explicit_state_context=False,
            )
        )

    def test_explicit_state_question_bypasses_state_context(self) -> None:
        route = route_assistant_message("Show me state changes around the last stop")
        self.assertTrue(route["explicit_state_context"])
        self.assertFalse(route["explicit_speed_context"])
        self.assertTrue(_is_explicit_state_context_request("Show me state changes around the last stop"))

    def test_dependent_speed_moves_to_context_by_default(self) -> None:
        self.assertTrue(
            _is_dependent_speed_context_row(
                {
                    "display_name": "current speed",
                    "opc_path": "Global PV/265 - hotmelt - bottom forming/state/nozzle - a-side/current speed",
                    "label": "nozzle - a-side / current speed",
                },
                explicit_speed_context=False,
            )
        )

    def test_default_filter_excludes_machine_speed(self) -> None:
        self.assertTrue(_is_machine_speed_context_row({"tag_id": 221}, 221))

    def test_default_filter_detects_dependent_speed_even_when_explicit_speed(self) -> None:
        row = {
            "display_name": "current speed",
            "opc_path": "Global PV/265 - hotmelt - bottom forming/state/nozzle - a-side/current speed",
            "label": "nozzle - a-side / current speed",
        }
        self.assertTrue(_is_dependent_speed_row(row))
        self.assertFalse(_is_dependent_speed_context_row(row, explicit_speed_context=True))

    def test_explicit_speed_question_bypasses_dependent_speed_context(self) -> None:
        route = route_assistant_message("Show me speed changes around the last stop")
        self.assertTrue(route["explicit_speed_context"])
        self.assertFalse(route["explicit_state_context"])
        self.assertTrue(_is_explicit_speed_context_request("Show me speed changes around the last stop"))

    def test_active_alarms_sets_alarm_context_only(self) -> None:
        route = route_assistant_message("Show active alarms around the last stop")
        self.assertTrue(route["explicit_alarm_context"])
        self.assertFalse(route["explicit_speed_context"])
        self.assertFalse(route["explicit_state_context"])
        self.assertTrue(_is_explicit_alarm_context_request("Show active alarms around the last stop"))

    def test_plc_context_request(self) -> None:
        self.assertTrue(_is_explicit_plc_context_request("Show PLC controller health"))

    def test_io_context_requires_standalone_token(self) -> None:
        self.assertTrue(has_explicit_plc_context("show io status"))
        self.assertTrue(has_explicit_plc_context("show i/o status"))
        self.assertFalse(has_explicit_plc_context("production"))
        self.assertFalse(route_assistant_message("production")["explicit_plc_context"])

    def test_counter_context_request(self) -> None:
        self.assertTrue(_is_explicit_counter_context_request("Show package counter values"))

    def test_default_filter_excludes_alarm_rows(self) -> None:
        reason = _filter_process_row(
            {"tag_id": 1, "section_key": "alarm system", "opc_path": "Global PV/alarm system/active alarms", "label": "active alarms"},
            apply_process_filters=True,
            explicit_alarm_context=False,
            explicit_counter_context=False,
            explicit_plc_context=False,
        )
        self.assertIsNotNone(reason)

    def test_default_filter_excludes_counter_rows(self) -> None:
        reason = _filter_process_row(
            {"tag_id": 1, "section_key": "format", "opc_path": "Global PV/info/state/package counter", "label": "package counter"},
            apply_process_filters=True,
            explicit_alarm_context=False,
            explicit_counter_context=False,
            explicit_plc_context=False,
        )
        self.assertEqual(reason, "excluded_tag_term")

    def test_default_filter_excludes_plc_rows(self) -> None:
        reason = _filter_process_row(
            {"tag_id": 1, "section_key": "i", "opc_path": "Global PV/i/o/plc temperature", "label": "plc temperature"},
            apply_process_filters=True,
            explicit_alarm_context=False,
            explicit_counter_context=False,
            explicit_plc_context=False,
        )
        self.assertIsNotNone(reason)

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

    def test_dedupe_keeps_one_row_for_duplicate_opc_path(self) -> None:
        rows = dedupe_rows(
            [
                {"opc_path": "A/B/C", "label": "x", "movement_score": 1, "range_value": 1},
                {"opc_path": "a/b/c", "label": "x", "movement_score": 3, "range_value": 2},
            ],
            lambda row: (row["movement_score"], row["range_value"]),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["movement_score"], 3)

    def test_section_summary_duplicate_labels_use_section_context(self) -> None:
        labels = _top_labels(
            [
                {"label": "current diameter", "section_key": "020 - unwinder"},
                {"label": "current diameter", "section_key": "300 - unwinder - bottom layer"},
            ],
            limit=2,
        )
        self.assertEqual(
            labels,
            [
                "current diameter in 020 - unwinder",
                "current diameter in 300 - unwinder - bottom layer",
            ],
        )

    def test_zero_score_rows_removed_from_default_around_stop_visible_rows(self) -> None:
        before, after = _rank_visible_around_stop_rows(
            [
                {
                    "opc_path": "Global PV/020 - unwinder/state/current diameter",
                    "label": "current diameter",
                    "section_key": "020 - unwinder",
                    "before_movement_score": 0,
                    "after_effect_score": 0,
                    "movement_score": 0,
                    "before_stop_movement": 0,
                    "after_stop_effect": 0,
                },
                {
                    "opc_path": "Global PV/020 - unwinder/state/web tension/currentPressure",
                    "label": "web tension / currentPressure",
                    "section_key": "020 - unwinder",
                    "before_movement_score": 2,
                    "after_effect_score": 0,
                    "movement_score": 1,
                    "before_stop_movement": 4,
                    "after_stop_effect": 0,
                },
            ],
            10,
        )
        self.assertEqual(len(before), 1)
        self.assertEqual(len(after), 0)

    def test_production_warning_helper(self) -> None:
        warnings = _production_warnings(7, 654, 661, round((654 / 661) * 100, 2))
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
