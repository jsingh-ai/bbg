from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.services import assistant_context
from app.services.assistant_context import (
    apply_followup_context,
    clear_all_conversations,
    clear_conversation,
    get_recent_turns,
    remember_turn,
)
from app.services.assistant_router import route_assistant_message


class AssistantContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_settings = assistant_context._settings
        assistant_context._settings = lambda: SimpleNamespace(
            assistant_context_enabled=True,
            assistant_context_max_age_minutes=120,
            assistant_context_max_turns=5,
            assistant_context_max_conversations=200,
            assistant_context_message_max_chars=500,
        )
        clear_conversation("followup-prod")
        clear_conversation("followup-stops")
        clear_conversation("followup-section")
        clear_conversation("followup-compare")
        clear_conversation("followup-limit")

    def tearDown(self) -> None:
        clear_all_conversations()
        assistant_context._settings = self.original_settings

    def test_time_range_only_followup_inherits_intent(self) -> None:
        remember_turn(
            "followup-prod",
            "How was production today?",
            route_assistant_message("How was production today?"),
            {"stop_time": None},
        )
        route = apply_followup_context(
            "What about this week?",
            route_assistant_message("What about this week?"),
            get_recent_turns("followup-prod"),
        )
        self.assertEqual(route["intent"], "production_summary")
        self.assertEqual(route["time_range"], "last_week")
        self.assertTrue(route["followup"]["used_context"])
        self.assertEqual(route["followup"]["original_intent"], "fallback")
        self.assertEqual(route["followup"]["resolved_intent"], "production_summary")

    def test_new_intent_inherits_previous_time_range(self) -> None:
        remember_turn(
            "followup-stops",
            "How many stops this week?",
            route_assistant_message("How many stops this week?"),
            {"stop_time": None},
        )
        route = apply_followup_context(
            "What about bags?",
            route_assistant_message("What about bags?"),
            get_recent_turns("followup-stops"),
        )
        self.assertEqual(route["intent"], "production_summary")
        self.assertEqual(route["time_range"], "last_week")
        self.assertTrue(route["followup"]["changed_time_range"])

    def test_stop_followup_inherits_previous_time_range(self) -> None:
        remember_turn(
            "followup-prod",
            "How was production last week?",
            route_assistant_message("How was production last week?"),
            {"stop_time": None},
        )
        route = apply_followup_context(
            "What about stops?",
            route_assistant_message("What about stops?"),
            get_recent_turns("followup-prod"),
        )
        self.assertEqual(route["intent"], "stop_summary")
        self.assertEqual(route["time_range"], "last_week")
        self.assertEqual(route["matched_rule"], "followup_resolved_subject_and_inherited_time")

    def test_section_followup_can_preserve_previous_process_intent(self) -> None:
        remember_turn(
            "followup-section",
            "What changed around the last stop?",
            route_assistant_message("What changed around the last stop?"),
            {"stop_time": "2026-06-25T10:00:00"},
        )
        route = apply_followup_context(
            "What about unwinder?",
            route_assistant_message("What about unwinder?"),
            get_recent_turns("followup-section"),
        )
        self.assertEqual(route["intent"], "values_around_last_stop")
        self.assertEqual(route["time_range"], "today")
        self.assertEqual(route["resolved_system"], "unwinder")
        self.assertIn("unwinder", route["section_terms"])

    def test_explicit_compare_does_not_inherit_previous_time_range(self) -> None:
        remember_turn(
            "followup-compare",
            "How was production last week?",
            route_assistant_message("How was production last week?"),
            {"stop_time": None},
        )
        route = apply_followup_context(
            "Compare today to yesterday",
            route_assistant_message("Compare today to yesterday"),
            get_recent_turns("followup-compare"),
        )
        self.assertEqual(route["intent"], "production_summary")
        self.assertEqual(route["time_range"], "today")
        self.assertEqual(route["compare_to"], "yesterday")
        self.assertFalse(route["followup"]["used_context"])

    def test_unrelated_compare_speed_does_not_inherit_production(self) -> None:
        remember_turn(
            "followup-compare",
            "How was production today?",
            route_assistant_message("How was production today?"),
            {"stop_time": None},
        )
        route = apply_followup_context(
            "Compare speed",
            route_assistant_message("Compare speed"),
            get_recent_turns("followup-compare"),
        )
        self.assertNotEqual(route["intent"], "production_summary")
        self.assertFalse(route["followup"]["used_context"])

    def test_followup_metadata_has_original_and_resolved_intent(self) -> None:
        remember_turn(
            "followup-prod",
            "How was production today?",
            route_assistant_message("How was production today?"),
            {"stop_time": None},
        )
        route = apply_followup_context(
            "What about this week?",
            route_assistant_message("What about this week?"),
            get_recent_turns("followup-prod"),
        )
        self.assertEqual(route["followup"]["original_intent"], "fallback")
        self.assertEqual(route["followup"]["resolved_intent"], "production_summary")
        self.assertTrue(route["followup"]["changed_intent"])

    def test_missing_context_does_not_alter_route(self) -> None:
        route = route_assistant_message("What about this week?")
        applied = apply_followup_context("What about this week?", route, [])
        self.assertEqual(applied["intent"], route["intent"])
        self.assertEqual(applied["time_range"], route["time_range"])
        self.assertFalse(applied["followup"]["used_context"])

    def test_remember_turn_keeps_only_newest_five(self) -> None:
        for index in range(6):
            remember_turn(
                "followup-limit",
                f"Message {index}",
                route_assistant_message("How was production today?"),
                {"stop_time": None},
            )
        turns = get_recent_turns("followup-limit")
        self.assertEqual(len(turns), 5)
        self.assertEqual(turns[0]["message"], "Message 1")
        self.assertEqual(turns[-1]["message"], "Message 5")

    def test_missing_conversation_id_stores_nothing(self) -> None:
        remember_turn(None, "How was production today?", route_assistant_message("How was production today?"), {"stop_time": None})
        self.assertEqual(get_recent_turns(None), [])

    def test_conversation_store_evicts_oldest_when_max_count_exceeded(self) -> None:
        assistant_context._settings = lambda: SimpleNamespace(
            assistant_context_enabled=True,
            assistant_context_max_age_minutes=120,
            assistant_context_max_turns=5,
            assistant_context_max_conversations=2,
            assistant_context_message_max_chars=500,
        )
        remember_turn("one", "How was production today?", route_assistant_message("How was production today?"), {"stop_time": None})
        remember_turn("two", "How was production today?", route_assistant_message("How was production today?"), {"stop_time": None})
        remember_turn("three", "How was production today?", route_assistant_message("How was production today?"), {"stop_time": None})
        self.assertEqual(get_recent_turns("one"), [])
        self.assertEqual(len(get_recent_turns("two")), 1)
        self.assertEqual(len(get_recent_turns("three")), 1)

    def test_remember_turn_truncates_message(self) -> None:
        assistant_context._settings = lambda: SimpleNamespace(
            assistant_context_enabled=True,
            assistant_context_max_age_minutes=120,
            assistant_context_max_turns=5,
            assistant_context_max_conversations=200,
            assistant_context_message_max_chars=8,
        )
        remember_turn("truncate", "1234567890", route_assistant_message("How was production today?"), {"stop_time": None})
        self.assertEqual(get_recent_turns("truncate")[0]["message"], "12345678")

    def test_clear_conversation_clears_only_one_conversation(self) -> None:
        remember_turn("keep", "How was production today?", route_assistant_message("How was production today?"), {"stop_time": None})
        remember_turn("clear", "How was production today?", route_assistant_message("How was production today?"), {"stop_time": None})
        clear_conversation("clear")
        self.assertEqual(get_recent_turns("clear"), [])
        self.assertEqual(len(get_recent_turns("keep")), 1)


if __name__ == "__main__":
    unittest.main()
