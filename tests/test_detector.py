"""Tests for the early-detection classifier (founder-before-official)."""
import unittest

from yc_monitor.detector import Post, classify_post, classify_many
from yc_monitor.index import build_index
from yc_monitor.models import STATUS_EARLY, STATUS_CONFIRMED


def _index():
    yc = [
        {"name": "Airbnb", "slug": "airbnb", "url": "https://www.ycombinator.com/companies/airbnb"},
        {"name": "Acme AI", "slug": "acme-ai", "url": "https://www.ycombinator.com/companies/acme-ai"},
    ]
    sr = [
        {"name": "Bead AI", "slug": "bead-ai", "x_url": "https://x.com/bead_ai",
         "url": "https://speedrun.a16z.com/companies/bead-ai"},
    ]
    return build_index(yc, sr)


class TestClassifier(unittest.TestCase):
    def test_early_unknown_company(self):
        # The example: founder announces acceptance, company not in directory.
        post = Post(source="X (Twitter)", author="Bek", author_handle="beknabdik",
                    text="big news: i got into Y Combinator. solo founder, on my 4th attempt.",
                    url="https://x.com/beknabdik/status/2061493360150601738", post_id="2061493360150601738")
        alert = classify_post(post, _index())
        self.assertEqual(alert.status, STATUS_EARLY)
        self.assertTrue(alert.extra.get("unmatched"))

    def test_confirmed_known_company(self):
        post = Post(source="X (Twitter)", author="Jane", author_handle="janedoe",
                    text="Acme AI is in the new YC batch! 🚀",
                    url="https://x.com/janedoe/status/1", post_id="1")
        alert = classify_post(post, _index())
        self.assertEqual(alert.status, STATUS_CONFIRMED)
        self.assertEqual(alert.company, "Acme AI")

    def test_handle_match(self):
        post = Post(source="X (Twitter)", author="Bead", author_handle="bead_ai",
                    text="We're in the a16z speedrun cohort!", url="https://x.com/bead_ai/status/2", post_id="2")
        alert = classify_post(post, _index())
        self.assertEqual(alert.status, STATUS_CONFIRMED)
        self.assertEqual(alert.company, "Bead AI")

    def test_dedup_keys_unique(self):
        posts = [
            Post(source="X (Twitter)", author="A", post_id="1", text="got into YC"),
            Post(source="LinkedIn", author="A", post_id="1", text="got into YC"),
        ]
        alerts = classify_many(posts, _index())
        self.assertNotEqual(alerts[0].dedup_key, alerts[1].dedup_key)


if __name__ == "__main__":
    unittest.main()
