"""Tests for packaged integration metadata and brand assets."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import unittest


REPOSITORY_ROOT = Path(__file__).parents[1]
COMPONENT_ROOT = REPOSITORY_ROOT / "custom_components" / "edc_sharing"


class TranslationMetadataTest(unittest.TestCase):
    def test_runtime_translations_match_source_entity_keys(self) -> None:
        source = json.loads((COMPONENT_ROOT / "strings.json").read_text(encoding="utf-8"))
        english = json.loads(
            (COMPONENT_ROOT / "translations" / "en.json").read_text(encoding="utf-8")
        )
        czech = json.loads(
            (COMPONENT_ROOT / "translations" / "cs.json").read_text(encoding="utf-8")
        )

        self.assertEqual(source["entity"], english["entity"])
        source_options = source["options"]["step"]["init"]
        english_options = english["options"]["step"]["init"]
        czech_options = czech["options"]["step"]["init"]
        self.assertEqual(
            source_options["data_description"],
            english_options["data_description"],
        )
        self.assertEqual(
            set(source_options["data_description"]),
            set(czech_options["data_description"]),
        )
        self.assertEqual(
            set(source["entity"]["button"]), set(czech["entity"]["button"])
        )
        source_entities = source["entity"]["sensor"]
        self.assertEqual(set(source_entities), set(czech["entity"]["sensor"]))
        for translations in (english, czech):
            names = [item["name"] for item in translations["entity"]["sensor"].values()]
            self.assertEqual(len(names), 16)
            self.assertEqual(len(names), len(set(names)))

        self.assertEqual(len(source["entity"]["button"]), 5)


class BrandMetadataTest(unittest.TestCase):
    def test_icon_sizes_and_transparency(self) -> None:
        for filename, expected_size in (("icon.png", 256), ("icon@2x.png", 512)):
            data = (COMPONENT_ROOT / "brand" / filename).read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            width, height = struct.unpack(">II", data[16:24])
            self.assertEqual((width, height), (expected_size, expected_size))
            self.assertIn(data[25], (4, 6), "Brand icon must contain an alpha channel")


if __name__ == "__main__":
    unittest.main()
