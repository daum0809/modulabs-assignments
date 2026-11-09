"""승인 기준 — 모두 코드로 계산한다 (LLM 판단 없음).

하나라도 걸리면 원장 승인 대기열로 보내고, 하나도 안 걸리면 자동 발송한다.
"""
from __future__ import annotations

import re

COMPARISON_WORDS = ["지난번보다", "지난 시간보다", "지난주보다", "여전히", "좋아졌", "나아졌", "향상되었", "늘었"]
SENSITIVE_WORDS = ["환불", "퇴원", "그만두", "자리", "교실 이동", "다툼", "싸움", "상담 요청", "학폭"]
ABSENCE_LIMIT = 3

ROOM_RE = re.compile(r"\d+\s*호(?:실)?")
PAGE_RE = re.compile(r"\d+\s*(?:쪽|페이지)|p\.?\s*\d+", re.IGNORECASE)

RULES = {
    "R1": {
        "title": "다른 학생 이름",
        "how": "학원 학생 명단(성+이름, 이름만)과 본문을 문자열 대조",
        "risk": "다른 학생의 개인정보가 학부모에게 새어 나감",
    },
    "R2": {
        "title": "강의실·교재 쪽수",
        "how": "정규식 `\\d+호`, `\\d+쪽|페이지|p.\\d+`",
        "risk": "내부 운영 정보 노출, 학부모가 쪽수만으로 진도를 오해",
    },
    "R3": {
        "title": "근거 없는 비교",
        "how": f"비교 표현({', '.join(COMPARISON_WORDS[:4])} 등)이 있는데 이전 발송 기록이 0건",
        "risk": "기록에 없는 '성장 이야기'를 지어내 신뢰를 잃음",
    },
    "R4": {
        "title": "민감 주제·결석",
        "how": f"민감 단어 목록 매칭 또는 이번 달 결석 {ABSENCE_LIMIT}회 이상",
        "risk": "상담이 필요한 내용이 자동 문자로 나가 갈등이 커짐",
    },
}


def _names_to_match(full: str) -> list[str]:
    out = [full]
    if len(full) >= 3:
        out.append(full[1:])
    return out


def check_message(text: str, student: dict, roster: list[str]) -> list[dict]:
    hits: list[dict] = []

    # R1 다른 학생 이름
    for other in roster:
        if other == student["name"]:
            continue
        for token in _names_to_match(other):
            if token in text:
                hits.append({"rule": "R1", "match": token, "detail": f"다른 학생 '{other}' 언급"})
                break

    # R2 강의실 번호·교재 쪽수
    for m in ROOM_RE.finditer(text):
        hits.append({"rule": "R2", "match": m.group(), "detail": "강의실 번호"})
    for m in PAGE_RE.finditer(text):
        hits.append({"rule": "R2", "match": m.group(), "detail": "교재 쪽수"})

    # R3 이전 기록 없이 비교 표현
    if student.get("history_count", 0) == 0:
        for w in COMPARISON_WORDS:
            if w in text:
                hits.append({"rule": "R3", "match": w, "detail": "이전 발송 기록 0건인데 비교 표현"})

    # R4 민감 주제·결석
    for w in SENSITIVE_WORDS:
        if w in text:
            hits.append({"rule": "R4", "match": w, "detail": "민감 단어"})
    if student.get("absences", 0) >= ABSENCE_LIMIT:
        hits.append({"rule": "R4", "match": f"결석은 {student['absences']}회", "detail": f"이번 달 결석 {student['absences']}회 (기준 {ABSENCE_LIMIT}회)"})

    return hits
