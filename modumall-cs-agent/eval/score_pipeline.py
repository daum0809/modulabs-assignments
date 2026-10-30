"""8강: 전체 그래프를 평가셋으로 채점하고, 틀린 케이스를 부품별로 나눈다.

실행: python -m eval.score_pipeline --router llm
"""
import argparse
from collections import Counter

from eval.metrics import load_eval_set
from graph import build_graph


def diagnose(case: dict, result: dict) -> str | None:
    """틀렸으면 책임 부품 이름, 맞았으면 None."""
    if result["route"] != case["route"]:
        return "route"
    escalated = bool(result.get("escalated"))
    if escalated != case["escalate"]:
        if not escalated:
            return "escalate(놓침)"
        return "guard" if result.get("unsupported_numbers") else "escalate(과잉)"
    if not escalated:
        missing = [s for s in case["must_include"] if s not in result["answer"]]
        if missing:
            return "answer"
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", choices=["rule", "llm"], default="llm")
    args = parser.parse_args()

    app = build_graph(args.router)
    cases = load_eval_set()
    blame = Counter()
    for case in cases:
        result = app.invoke({"question": case["text"]})
        part = diagnose(case, result)
        blame[part or "정답"] += 1
        status = "O" if part is None else f"X [{part}]"
        print(f"{status:<18} {case['id']} {case['text']}")
        if part:
            print(f"    route={result['route']} 확신도={result['confidence']} 이관사유={result.get('escalate_reason')}")
            if part == "guard":
                print(f"    가드에 걸린 답변: {result.get('draft_answer', '')[:200]}")

    print(f"\n정답 {blame.pop('정답', 0)}/{len(cases)}")
    for part, n in blame.most_common():
        print(f"  {part}: {n}")


if __name__ == "__main__":
    main()
