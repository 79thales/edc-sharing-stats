"""Tests for packaged integration metadata and brand assets."""

from __future__ import annotations

import json
from pathlib import Path
import re
import struct
import unittest


REPOSITORY_ROOT = Path(__file__).parents[1]
COMPONENT_ROOT = REPOSITORY_ROOT / "custom_components" / "edc_sharing"
TEXT_SUFFIXES = {".json", ".md", ".py", ".yaml", ".yml"}
NON_EMAIL_LITERALS = {"icon@2x.png"}


def _repository_text_files():
    """Yield repository files that may contain accidentally committed private data."""
    for root in (
        REPOSITORY_ROOT / ".github",
        REPOSITORY_ROOT / "custom_components",
        REPOSITORY_ROOT / "tests",
    ):
        yield from (path for path in root.rglob("*") if path.suffix in TEXT_SUFFIXES)
    yield REPOSITORY_ROOT / "README.md"
    yield REPOSITORY_ROOT / "CHANGELOG.md"
    yield REPOSITORY_ROOT / "hacs.json"


class RepositoryPrivacyTest(unittest.TestCase):
    def test_no_ean_literals_are_committed(self) -> None:
        pattern = re.compile(r"(?<!\d)\d{18}(?!\d)")
        violations = [
            str(path.relative_to(REPOSITORY_ROOT))
            for path in _repository_text_files()
            if pattern.search(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual([], violations)

    def test_committed_email_literals_are_examples(self) -> None:
        pattern = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
        violations = []
        for path in _repository_text_files():
            emails = pattern.findall(path.read_text(encoding="utf-8"))
            if any(
                email not in NON_EMAIL_LITERALS
                and not email.casefold().endswith("@example.com")
                for email in emails
            ):
                violations.append(str(path.relative_to(REPOSITORY_ROOT)))
        self.assertEqual([], violations)


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
        self.assertEqual(source_options["data"], english_options["data"])
        self.assertEqual(
            set(source_options["data_description"]),
            set(czech_options["data_description"]),
        )
        self.assertEqual(set(source_options["data"]), set(czech_options["data"]))
        self.assertIn("summary_report", source_options["data"])
        self.assertEqual(
            set(source["entity"]["button"]), set(czech["entity"]["button"])
        )
        source_entities = source["entity"]["sensor"]
        self.assertEqual(set(source_entities), set(czech["entity"]["sensor"]))
        for translations in (english, czech):
            names = [item["name"] for item in translations["entity"]["sensor"].values()]
            self.assertEqual(len(names), 19)
            self.assertEqual(len(names), len(set(names)))

        self.assertEqual(len(source["entity"]["button"]), 7)


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
