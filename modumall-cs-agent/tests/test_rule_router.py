import unittest

from routers import rule_route


class RuleRouterTest(unittest.TestCase):
    def test_bundle_beats_return(self):
        route, _, _ = rule_route("세트에서 하나만 반품할래요")
        self.assertEqual(route, "bundle")

    def test_no_match_is_other_with_zero_confidence(self):
        self.assertEqual(rule_route("안녕하세요")[:2], ("other", 0.0))


if __name__ == "__main__":
    unittest.main()
