import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compose import compose_draft  # noqa: E402
from graph import Pipeline  # noqa: E402
from rules import check_message  # noqa: E402

STUDENTS = json.loads((ROOT / "data" / "students.json").read_text(encoding="utf-8"))
ROSTER = [s["name"] for s in STUDENTS]
BY_ID = {s["id"]: s for s in STUDENTS}


def rules_for(sid):
    s = BY_ID[sid]
    return sorted({h["rule"] for h in check_message(compose_draft(s), s, ROSTER)})


class RuleTests(unittest.TestCase):
    def test_planted_cases(self):
        self.assertEqual(rules_for("S02"), ["R1"])        # 다른 학생 이름(지호)
        self.assertEqual(rules_for("S04"), ["R2"])        # 교재 쪽수
        self.assertEqual(rules_for("S05"), ["R2", "R4"])  # 302호 + 자리
        self.assertEqual(rules_for("S06"), ["R3"])        # 기록 0건 + 비교
        self.assertEqual(rules_for("S08"), ["R4"])        # 결석 3회
        self.assertEqual(rules_for("S11"), ["R4"])        # 환불

    def test_comparison_allowed_with_history(self):
        self.assertEqual(rules_for("S07"), [])  # 기록 3건이면 '지난번보다' 허용

    def test_clean_students_pass(self):
        for sid in ["S01", "S03", "S07", "S09", "S10", "S12", "S13", "S14"]:
            self.assertEqual(rules_for(sid), [], sid)

    def test_own_name_is_not_a_hit(self):
        s = BY_ID["S01"]
        self.assertEqual(check_message("서준이가 잘했습니다.", s, ROSTER), [])


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.p = Pipeline(Path(tempfile.mkdtemp()))
        self.res = self.p.run_batch(STUDENTS)

    def find(self, name):
        return next(x for x in self.p.pending() if x["student"] == name)

    def test_batch_splits_auto_and_pending(self):
        self.assertEqual(self.res["auto_sent"], 8)
        self.assertEqual(self.res["pending"], 6)
        self.assertEqual(len(self.p.outbox.all()), 8)  # 대기 건은 발송함에 없음

    def test_approve_resumes_and_sends(self):
        item = self.find("임채원")
        self.assertEqual(self.p.resume(item["thread_id"], {"action": "approve"})["status"], "approved_sent")
        sent = [r for r in self.p.outbox.all() if r["student"] == "임채원"]
        self.assertEqual(sent[0]["decisions"][0]["rules"], ["R4"])

    def test_edit_is_rechecked(self):
        item = self.find("최예린")
        half = item["draft"].replace("45쪽부터 ", "")
        self.assertEqual(self.p.resume(item["thread_id"], {"action": "edit", "text": half})["status"], "pending")
        fixed = item["draft"].replace("교재 45쪽부터 52쪽까지 숙제로", "오늘 숙제를")
        self.assertEqual(self.p.resume(item["thread_id"], {"action": "edit", "text": fixed})["status"], "approved_sent")

    def test_reject_is_not_sent(self):
        item = self.find("정민재")
        self.assertEqual(self.p.resume(item["thread_id"], {"action": "reject"})["status"], "rejected")
        self.assertEqual(self.p.summary([item["thread_id"]])["rejected"], 1)
        self.assertNotIn(item["thread_id"], [x["thread_id"] for x in self.p.pending()])

    def test_survives_restart(self):
        p2 = Pipeline(self.p.dir)  # 새 프로세스처럼 다시 열어도 대기 건 유지
        self.assertEqual(len(p2.pending()), 6)


class AppTests(unittest.TestCase):
    def test_app_runs_end_to_end(self):
        from streamlit.testing.v1 import AppTest
        os.environ["GROWNOTE_DATA_DIR"] = tempfile.mkdtemp()
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
        self.assertFalse(at.exception)
        at.button(key="run").click().run()
        self.assertFalse(at.exception)
        self.assertIn("② 승인 대기함 (6)", [t.label for t in at.tabs])
        ok = [b for b in at.button if b.key and b.key.startswith("ok-")][0]
        ok.click().run()
        self.assertFalse(at.exception)
        self.assertIn("② 승인 대기함 (5)", [t.label for t in at.tabs])


if __name__ == "__main__":
    unittest.main(verbosity=2)
