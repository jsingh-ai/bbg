from __future__ import annotations

import unittest

from app.services.section_knowledge import get_section_knowledge


class SectionKnowledgeTests(unittest.TestCase):
    def test_matches_station_number_independently_of_label_text(self) -> None:
        result = get_section_knowledge("86 - PRINT MARK - NEEDLE PERFORATION")

        self.assertEqual(result["sequence_number"], "086")
        self.assertEqual(result["process_stage"], "Perforation registration")
        self.assertIn("does not make the holes", result["process_description"] or "")

    def test_bottom_layer_is_described_as_bottom_patch(self) -> None:
        result = get_section_knowledge("300 - unwinder - bottom layer")

        self.assertEqual(result["process_stage"], "Bottom-patch supply")
        self.assertIn("bottom-patch roll", result["process_description"] or "")

    def test_scrap_section_has_training_description(self) -> None:
        result = get_section_knowledge("scrap")

        self.assertIsNone(result["sequence_number"])
        self.assertEqual(result["process_stage"], "Waste and rejection")

    def test_unknown_section_returns_empty_training_fields(self) -> None:
        result = get_section_knowledge("alarm system")

        self.assertIsNone(result["process_stage"])
        self.assertIsNone(result["process_description"])


if __name__ == "__main__":
    unittest.main()
