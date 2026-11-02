"""8강: 전체 그래프를 평가셋으로 채점한다.

- 답변 품질은 eval/answer_rubric.py의 기준(R1~R5)으로 채점한다.
- 틀린 문항은 책임 부품(route / escalate / guard / answer)으로 나눈다.
- 문항별 답변 전문을 eval/results/<set>.jsonl에 저장한다. 실패 분석은 이 파일을 직접 읽고 한다.

실행: python -m eval.score_pipeline --router llm --set dev
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from eval.answer_rubric import CRITERIA, grade, passed
from eval.metrics import load_eval_set
from graph import build_graph

RESULTS_DIR = Path(__file__).parent / "results"


def diagnose(grades: dict, result: dict) -> str | None:
    """틀렸으면 책임 부품 이름, 맞았으면 None."""
    if grades["R1_분류"] is False:
        return "route"
    if grades["R2_이관"] is False:
        if not result.get("escalated"):
            return "escalate(놓침)"
        return "guard" if result.get("unsupported_numbers") else "escalate(과잉)"
    if not passed(grades):
        return "answer"
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", choices=["rule", "llm"], default="llm")
    parser.add_argument("--set", choices=["dev", "test"], default="dev")
    args = parser.parse_args()

    app = build_graph(args.router)
    cases = load_eval_set(args.set)
    blame = Counter()
    criterion = Counter()
    applicable = Counter()
    rows = []
    for case in cases:
        result = app.invoke({"question": case["text"]})
        grades = grade(case, result)
        part = diagnose(grades, result)
        blame[part or "정답"] += 1
        for key, value in grades.items():
            if value is not None:
                applicable[key] += 1
                criterion[key] += value
        status = "O" if part is None else f"X [{part}]"
        print(f"{status:<18} {case['id']} {case['text']}")
        if part:
            failed = [k for k, v in grades.items() if v is False]
            print(f"    실패 기준={failed} route={result['route']} 확신도={result['confidence']} 이관사유={result.get('escalate_reason')}")
        rows.append({
            "id": case["id"], "text": case["text"], "expected_route": case["route"],
            "expected_escalate": case["escalate"], "route": result["route"], "confidence": result["confidence"],
            "route_reason": result.get("route_reason"), "escalated": bool(result.get("escalated")),
            "escalate_reason": result.get("escalate_reason"), "answer": result.get("answer", ""),
            "draft_answer": result.get("draft_answer", ""), "unsupported_numbers": result.get("unsupported_numbers", []),
            "grades": grades, "blame": part,
        })

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{args.set}.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    print(f"\n[{args.router} 라우터 · {args.set} {len(cases)}문항]")
    print(f"전체 통과: {blame.pop('정답', 0)}/{len(cases)}")
    for key, desc in CRITERIA.items():
        print(f"  {key:<12} {criterion[key]}/{applicable[key]}  {desc}")
    if blame:
        print("실패 원인(부품):", ", ".join(f"{k} {v}" for k, v in blame.most_common()))
    print(f"문항별 답변 저장: {out}")


if __name__ == "__main__":
    main()
