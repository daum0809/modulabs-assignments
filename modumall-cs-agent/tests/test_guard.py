import unittest

from guards import check_numbers, extract_numbers


class NumberGuardTest(unittest.TestCase):
    def test_extract_normalizes_commas_and_ranges(self):
        self.assertEqual(extract_numbers("배송비 3,000원, 1~2영업일"), {"3000", "1", "2"})

    def test_korean_units(self):
        self.assertEqual(extract_numbers("5만 원 이상, 3천원, 1.5만원"), {"50000", "3000", "15000"})

    def test_man_won_matches_manual_digits(self):
        ok, _ = check_numbers("5만 원 이상이면 무료입니다.", ["50,000원 이상이면 배송비는 무료다."])
        self.assertTrue(ok)

    def test_unit_changes_meaning(self):
        # "5만"은 5가 아니라 50000이므로 근거가 "5영업일"뿐이면 걸려야 한다
        ok, bad = check_numbers("5만 원입니다.", ["5영업일"])
        self.assertFalse(ok)
        self.assertEqual(bad, ["50000"])

    def test_number_in_manual_passes(self):
        ok, _ = check_numbers("반품 배송비는 6,000원입니다.", ["왕복 배송비 6,000원"])
        self.assertTrue(ok)

    def test_invented_number_fails(self):
        ok, bad = check_numbers("환불은 5일 걸립니다.", ["3영업일 이내에 환불"])
        self.assertFalse(ok)
        self.assertEqual(bad, ["5"])

    def test_tool_json_counts_as_source(self):
        ok, _ = check_numbers("결제 금액은 28,800원입니다.", ['{"total": 28800}'])
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
