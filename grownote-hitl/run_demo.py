"""REPORT.md용 실행 결과 만들기.

14명 일괄 실행 → 대기 6건에 원장 결정을 대본대로 입력 → results/demo_result.md 저장.
API 호출 없음.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from graph import Pipeline
from rules import RULES

BASE = Path(__file__).parent
OUT_DIR = BASE / "results"
DATA = BASE / "results" / "demo_runtime"

# 원장 결정 대본: (학생, 결정, 고친 문장을 만드는 함수)
SCRIPT = [
    ("이하윤", "edit", lambda t: t.replace("오늘은 지호랑 짝을 지어", "오늘은 친구와 짝을 지어")),
    ("최예린", "edit", lambda t: t.replace("교재 45쪽부터 ", "")),            # 일부러 덜 고침 → 다시 걸림
    ("최예린", "edit", lambda t: t.replace("52쪽까지 숙제로 냈습니다.", "오늘 배운 유형으로 숙제를 냈습니다.")),
    ("정민재", "reject", None),                                             # 자리 이동은 전화로 따로 안내
    ("강다은", "edit", lambda t: t.replace("지난번보다 계산 속도가 확실히 좋아졌어요.", "오늘은 계산을 끝까지 집중해서 했습니다.")),
    ("한소율", "approve", None),                                            # 결석 사실 확인 후 그대로 발송
    ("임채원", "reject", None),                                             # 환불 건은 문자 대신 상담
]


def main() -> None:
    if DATA.exists():
        shutil.rmtree(DATA)
    p = Pipeline(DATA)
    students = json.loads((BASE / "data" / "students.json").read_text(encoding="utf-8"))
    first = p.run_batch(students)
    threads = p.runs()[-1]["threads"]

    lines = ["# 실행 결과 (run_demo.py)", "",
             f"## 1단계: 일괄 실행 — {len(students)}명",
             f"- 자동 발송 **{first['auto_sent']}건**, 승인 대기 **{first['pending']}건**", "",
             "| 학생 | 걸린 기준 | 걸린 부분 |", "|---|---|---|"]
    for item in p.pending():
        rules = ", ".join(sorted({f"{h['rule']} {RULES[h['rule']]['title']}" for h in item["hits"]}))
        matches = ", ".join(f"`{h['match']}`" for h in item["hits"])
        lines.append(f"| {item['student']} | {rules} | {matches} |")

    lines += ["", "## 2단계: 원장 결정 → 그래프 재개", "", "| 학생 | 결정 | 재개 후 상태 | 남은 기준 |", "|---|---|---|---|"]
    for name, action, fix in SCRIPT:
        item = next(x for x in p.pending() if x["student"] == name)
        answer = {"action": action}
        if fix:
            answer["text"] = fix(item["draft"])
        r = p.resume(item["thread_id"], answer)
        left = ", ".join(f"`{h['match']}`" for h in r["hits"]) if r["status"] == "pending" else "—"
        lines.append(f"| {name} | {action} | {r['status']} | {left} |")

    final = p.summary(threads)
    rule_count = {k: 0 for k in RULES}
    for tid in threads:
        st = p.graph.get_state(p._cfg(tid)).values
        for d in st.get("decisions", [])[:1]:
            for k in d["rules"]:
                rule_count[k] += 1
    lines += ["", "## 3단계: 최종 결과",
              f"- 자동 발송 {final['auto_sent']} · 승인 후 발송 {final['approved_sent']} · 반려 {final['rejected']} · 대기 {final['pending']}",
              "- 기준별로 걸린 문자 수: " + ", ".join(f"{k} {v}건" for k, v in rule_count.items()),
              f"- 발송함 기록 {len(p.outbox.all())}건 (반려 포함, 같은 건 중복 기록 없음)", "",
              "## 원장이 결정한 건의 최종 본문", ""]
    for r in p.outbox.all():
        if r["decisions"]:
            lines.append(f"- **{r['student']}** ({r['status']}): {r['text']}")

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "demo_result.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    p.conn.close()
    print("\n".join(lines))


if __name__ == "__main__":
    main()
