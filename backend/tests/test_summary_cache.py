import unittest

from app.services.briefing_cache import get_cached_briefing


class SummaryCacheTests(unittest.TestCase):
    def test_raw_saved_briefing_is_reused(self):
        markdown = "## Executive Summary\nSaved report"

        self.assertEqual(get_cached_briefing(markdown), markdown)

    def test_versioned_saved_briefing_is_reused_without_internal_marker(self):
        markdown = (
            "<!-- briefing-context:correlations-v2 -->\n"
            "## Executive Summary\nSaved report"
        )

        self.assertEqual(
            get_cached_briefing(markdown),
            "## Executive Summary\nSaved report",
        )

    def test_missing_briefing_is_a_cache_miss(self):
        self.assertIsNone(get_cached_briefing(None))
        self.assertIsNone(get_cached_briefing(""))


if __name__ == "__main__":
    unittest.main()
