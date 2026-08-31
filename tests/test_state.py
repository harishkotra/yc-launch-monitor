"""Tests for state management, dedup, and Slack payload rendering."""
import os
import tempfile
import unittest

from yc_monitor.state import State
from yc_monitor.models import Alert, STATUS_EARLY, STATUS_CONFIRMED, make_dedup_key


class TestState(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.state = State(self.path)

    def tearDown(self):
        self.state.close()
        os.remove(self.path)

    def test_dedup_basic(self):
        key = make_dedup_key("yc", "nodus")
        self.assertFalse(self.state.is_seen(key))
        self.state.mark_seen(key, "YC Directory", "Nodus")
        self.assertTrue(self.state.is_seen(key))

    def test_dedup_key_normalization(self):
        self.assertEqual(make_dedup_key("YC", "Nodus"), make_dedup_key("yc", "nodus"))

    def test_snapshot_baseline(self):
        self.assertFalse(self.state.snapshot_unchanged("speedrun_all", ["a", "b"]))
        self.state.update_snapshot("speedrun_all", ["a", "b"])
        self.assertTrue(self.state.snapshot_unchanged("speedrun_all", ["a", "b"]))
        self.assertFalse(self.state.snapshot_unchanged("speedrun_all", ["a", "b", "c"]))


class TestSlackPayload(unittest.TestCase):
    def test_confirmed_payload_shape(self):
        alert = Alert(
            company="Nodus", source="YC Directory", status=STATUS_CONFIRMED,
            details="Intelligent execution layer for AI workloads.",
            link="https://www.ycombinator.com/companies/nodus",
            dedup_key="yc|nodus", extra={"batch": "Fall 2026"},
        )
        payload = alert.to_slack_payload({"slack": {"username": "Bot", "mention": ""}})
        self.assertEqual(payload["blocks"][0]["text"]["text"], "✅ Nodus")
        self.assertIn("Confirmed", payload["blocks"][1]["text"]["text"])
        self.assertIn("Fall 2026", payload["blocks"][2]["elements"][0]["text"])

    def test_early_payload_shape(self):
        alert = Alert(
            company="Unknown company", source="X (Twitter)", status=STATUS_EARLY,
            founder="Bek", details="big news: i got into Y Combinator.",
            link="https://x.com/beknabdik/status/2061493360150601738",
            dedup_key="x|123", extra={"author_handle": "beknabdik"},
        )
        payload = alert.to_slack_payload({"slack": {"username": "Bot", "mention": ""}})
        self.assertEqual(payload["blocks"][0]["text"]["text"], "⚡ Unknown company")
        self.assertIn("Early signal", payload["blocks"][1]["text"]["text"])
        # action button carries the original post link
        urls = [b.get("url") for blk in payload["blocks"]
                for b in (blk.get("elements") or []) if isinstance(b, dict)]
        self.assertIn("https://x.com/beknabdik/status/2061493360150601738", urls)


if __name__ == "__main__":
    unittest.main()
