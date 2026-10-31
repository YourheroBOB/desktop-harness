"""可重現的 safety 解析與驗證模糊測試；僅使用 Python 標準函式庫。"""
from __future__ import annotations

import json
import os
import random
import string
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from desktop_harness import safety  # noqa: E402


_SEED = 0xF06F22
_ASCII = string.ascii_letters + string.digits + " _-./"
_MIXED = _ASCII + string.punctuation + "\t\n\r雪éΩ"


def _text(rng: random.Random, *, alphabet: str = _MIXED, limit: int = 180) -> str:
    length = rng.randrange(limit + 1)
    return "".join(rng.choice(alphabet) for _ in range(length))


def _json_value(rng: random.Random, depth: int = 0):
    """建立不含外部資料、可 JSON 往返的合成值。"""
    if depth >= 2 or rng.randrange(4) == 0:
        return rng.choice((None, True, False, rng.randrange(-10_000, 10_001), _text(rng, limit=70)))
    if rng.randrange(2):
        return [_json_value(rng, depth + 1) for _ in range(rng.randrange(5))]
    return {
        f"k{index}_{rng.randrange(1_000)}": _json_value(rng, depth + 1)
        for index in range(rng.randrange(5))
    }


class SafetyFuzzTests(unittest.TestCase):
    def test_random_strings_do_not_crash(self):
        rng = random.Random(_SEED)
        for index in range(10_000):
            limit = 2_048 if index % 97 == 0 else 180
            name = _text(rng, limit=limit)
            bundle_id = _text(rng, limit=limit)
            result = safety._looks_sensitive(name, bundle_id)
            self.assertIsInstance(result, bool)

    def test_configured_sensitive_terms_match_case_insensitively(self):
        rng = random.Random(_SEED + 1)

        for term in safety._SENSITIVE_NAME_SUBSTR:
            for _ in range(120):
                prefix = _text(rng, alphabet=_ASCII, limit=50)
                suffix = _text(rng, alphabet=_ASCII, limit=50)
                mixed_term = "".join(
                    char.upper() if rng.randrange(2) else char.lower()
                    for char in term
                )
                candidate = prefix + mixed_term + suffix
                self.assertTrue(safety._looks_sensitive(candidate, ""))

        for term in safety._SENSITIVE_BUNDLE_SUBSTR:
            for _ in range(120):
                prefix = _text(rng, alphabet=_ASCII, limit=50)
                suffix = _text(rng, alphabet=_ASCII, limit=50)
                mixed_term = "".join(
                    char.upper() if rng.randrange(2) else char.lower()
                    for char in term
                )
                candidate = prefix + mixed_term + suffix
                self.assertTrue(safety._looks_sensitive("", candidate))

    def test_app_validation_agrees_with_sensitive_detection(self):
        rng = random.Random(_SEED + 2)
        terms = safety._SENSITIVE_NAME_SUBSTR + safety._SENSITIVE_BUNDLE_SUBSTR

        with patch.dict(os.environ, {"DH_ALLOW_SENSITIVE": "0"}):
            for index in range(6_000):
                name = _text(rng)
                bundle_id = _text(rng)
                if index % 3 == 0:
                    name += rng.choice(terms)
                elif index % 3 == 1:
                    bundle_id += rng.choice(terms)

                expected_block = safety._looks_sensitive(name, bundle_id)
                if expected_block:
                    with self.assertRaises(PermissionError):
                        safety.check_app_allowed(name, bundle_id)
                else:
                    safety.check_app_allowed(name, bundle_id)

    def test_environment_policy_parsers_for_random_values(self):
        rng = random.Random(_SEED + 3)
        allow_values = {"1", "true", "yes"}
        unsafe_values = {"0", "false", "no"}

        for _ in range(3_000):
            value = _text(rng, limit=80)
            lowered = value.lower()
            with patch.dict(os.environ, {
                "DH_ALLOW_SENSITIVE": value,
                "DH_SAFE": value,
            }):
                self.assertEqual(safety.allow_sensitive(), lowered in allow_values)
                self.assertEqual(safety.safe_mode(), lowered not in unsafe_values)

        for value in ("1", "TRUE", "yes"):
            with patch.dict(os.environ, {"DH_ALLOW_SENSITIVE": value}):
                self.assertTrue(safety.allow_sensitive())
        for value in ("0", "False", "NO"):
            with patch.dict(os.environ, {"DH_SAFE": value}):
                self.assertFalse(safety.safe_mode())

    def test_audit_random_json_records_round_trip_in_temp_directory(self):
        rng = random.Random(_SEED + 4)
        previous_audit_path = safety._AUDIT

        with tempfile.TemporaryDirectory(prefix="fmb-fuzz-") as temp_dir:
            audit_path = Path(temp_dir) / "audit.jsonl"
            safety._AUDIT = audit_path
            expected_rows = []

            try:
                for _ in range(400):
                    event = _text(rng, limit=100)
                    detail = {
                        f"field_{index}_{rng.randrange(10_000)}": _json_value(rng)
                        for index in range(rng.randrange(1, 6))
                    }
                    safety.audit(event, detail)
                    expected_rows.append((event, detail))

                lines = audit_path.read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(lines), len(expected_rows))

                for line, (expected_event, expected_detail) in zip(lines, expected_rows):
                    row = json.loads(line)
                    self.assertEqual(row["event"], expected_event)
                    self.assertEqual(row["detail"], expected_detail)
                    self.assertIsInstance(row["ts"], (int, float))
            finally:
                safety._AUDIT = previous_audit_path


if __name__ == "__main__":
    unittest.main()
