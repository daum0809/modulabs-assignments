"""3강: 키워드·정규식 규칙 라우터 (기준선)."""
import re

# 라우트별 (패턴, 가중치). 동점이면 이 dict 순서가 앞선 라우트가 이긴다.
RULES: dict[str, list[tuple[str, float]]] = {
    "bundle": [(r"세트", 2.0), (r"구성품", 2.0)],
    "order": [(r"취소", 2.0), (r"결제", 1.0), (r"배송지|주소", 1.5)],
    "return": [(r"반품", 2.0), (r"교환", 2.0), (r"환불", 1.5)],
    "delivery": [(r"배송|택배|송장", 1.0), (r"도착|언제 와|언제 오", 1.0), (r"제주|도서산간", 1.0)],
}


def rule_route(question: str) -> tuple[str, float, str]:
    """(route, confidence, reason)을 돌려준다. 아무 규칙도 안 맞으면 other, 확신도 0."""
    scores: dict[str, float] = {}
    hits: dict[str, list[str]] = {}
    for route, patterns in RULES.items():
        for pattern, weight in patterns:
            if re.search(pattern, question):
                scores[route] = scores.get(route, 0.0) + weight
                hits.setdefault(route, []).append(pattern)

    if not scores:
        return "other", 0.0, "일치하는 규칙 없음"

    best = max(scores, key=lambda r: scores[r])  # max는 동점이면 먼저 나온 것을 고른다
    confidence = scores[best] / sum(scores.values())
    return best, round(confidence, 2), f"규칙 일치: {hits[best]}"
