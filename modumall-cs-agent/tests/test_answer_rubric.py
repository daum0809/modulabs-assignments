import unittest

from eval.answer_rubric import passed
from eval.validate_scorer import disagreements, load


class ScorerValidityTest(unittest.TestCase):
    def test_scorer_agrees_with_human_labels(self):
        self.assertEqual(disagreements(load()), [])

    def test_not_applicable_does_not_fail(self):
        self.assertTrue(passed({"R1_분류": True, "R2_이관": True, "R3_필수정보": None}))
        self.assertFalse(passed({"R1_분류": True, "R2_이관": False, "R3_필수정보": None}))


if __name__ == "__main__":
    unittest.main()
