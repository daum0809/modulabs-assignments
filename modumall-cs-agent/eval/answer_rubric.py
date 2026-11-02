"""8강: 답변 품질 채점 기준 (채점 전에 정해 두고 바꾸지 않는다).

각 기준은 True(통과) / False(실패) / None(해당 없음)을 낸다.
이관된 문의는 고객에게 안내 문구만 나가므로 R3~R5는 '해당 없음'이다.
숫자는 글자가 아니라 값으로 비교한다: "50,000원" = "50000원" = "5만 원", 그러나 "17일" ≠ "7일".
"""
import re

from guards import check_numbers, extract_numbers

CRITERIA = {
    "R1_분류": "예측한 카테고리가 정답 카테고리와 같다",
    "R2_이관": "사람에게 넘겼는지가 정답과 같다 (넘겨야 할 문의는 넘기고, 답할 수 있는 문의는 답한다)",
    "R3_필수정보": "답변에 그 문의에 꼭 필요한 정보(must_include)가 모두 있다",
    "R4_정책혼입없음": "답변에 다른 카테고리 정책(must_not_include)이 섞이지 않았다",
    "R5_근거있는숫자": "답변의 모든 숫자가 근거 문서·조회 결과·질문에 있다",
}


def _mentions(answer: str, item: str) -> bool:
    """item에 숫자가 있으면 숫자 값으로, 없으면 글자로 비교한다."""
    if re.search(r"\d", item):
        return extract_numbers(item) <= extract_numbers(answer)
    return item in answer


def grade(case: dict, result: dict) -> dict[str, bool | None]:
    escalated = bool(result.get("escalated"))
    answer = result.get("answer", "")
    grades: dict[str, bool | None] = {
        "R1_분류": result["route"] == case["route"],
        "R2_이관": escalated == case["escalate"],
        "R3_필수정보": None,
        "R4_정책혼입없음": None,
        "R5_근거있는숫자": None,
    }
    if not escalated:
        grades["R3_필수정보"] = all(_mentions(answer, s) for s in case.get("must_include", []))
        grades["R4_정책혼입없음"] = not any(_mentions(answer, s) for s in case.get("must_not_include", []))
        grades["R5_근거있는숫자"] = check_numbers(answer, result.get("sources", []))[0]
    return grades


def passed(grades: dict[str, bool | None]) -> bool:
    return all(v is not False for v in grades.values())
