"""3·4강: 라우터만 평가셋으로 채점한다 (정확도, Macro F1, 혼동 행렬, 이관 판정).

실행: python -m eval.score_router --router rule --set dev
"""
import argparse

import config
from eval.metrics import accuracy, confusion_matrix_text, load_eval_set, macro_f1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", choices=["rule", "llm"], default="rule")
    parser.add_argument("--set", choices=["dev", "test"], default="dev")
    args = parser.parse_args()

    if args.router == "rule":
        from routers import rule_route as route_fn
    else:
        from routers.llm_router import llm_route as route_fn

    cases = load_eval_set(args.set)
    y_true, y_pred = [], []
    escalate_hits = 0
    for case in cases:
        route, confidence, _ = route_fn(case["text"])
        would_escalate = route == "other" or confidence < config.CONFIDENCE_THRESHOLD
        escalate_hits += would_escalate == case["escalate"]
        y_true.append(case["route"])
        y_pred.append(route)
        mark = "O" if route == case["route"] else "X"
        print(f"{mark} {case['id']} 정답={case['route']:<8} 예측={route:<8} 확신도={confidence:.2f} 이관={would_escalate!s:<5}  {case['text']}")

    score, per_label = macro_f1(y_true, y_pred)
    print(f"\n[{args.router} 라우터 · {args.set} {len(cases)}문항]")
    print(f"정확도: {accuracy(y_true, y_pred):.3f}")
    print(f"Macro F1: {score:.3f}")
    print(f"이관 판정 일치: {escalate_hits}/{len(cases)}")
    for label, m in per_label.items():
        print(f"  {label:<9} P={m['precision']:.2f} R={m['recall']:.2f} F1={m['f1']:.2f} (n={m['support']})")
    print("\n" + confusion_matrix_text(y_true, y_pred))


if __name__ == "__main__":
    main()
