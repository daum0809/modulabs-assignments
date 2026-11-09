"""학부모 피드백 문자 초안 작성.

API 크레딧 없이 돌아가도록 템플릿으로 만든다. 강사가 적은 '오늘 메모'는
그대로 본문에 들어가므로, 메모에 섞인 위험 정보(다른 학생 이름, 강의실 번호 등)가
초안까지 흘러온다. 승인 기준(rules.py)이 바로 그 지점을 잡는다.
LLM으로 바꾸려면 compose_draft 하나만 교체하면 된다.
"""
from __future__ import annotations


def _has_final_consonant(ch: str) -> bool:
    code = ord(ch) - 0xAC00
    return 0 <= code <= 11171 and code % 28 != 0


def call_name(name: str) -> str:
    """'김서준' -> '서준이', '박지호' -> '지호'."""
    given = name[1:] if len(name) >= 3 else name
    return given + ("이" if _has_final_consonant(given[-1]) else "")


def compose_draft(student: dict) -> str:
    who = call_name(student["name"])
    parts = [
        f"안녕하세요, {student['name']} 학부모님.",
        f"오늘 {who}는 {student['subject']} '{student['unit']}' 수업을 했습니다.",
        student["strength"],
        student["practice"],
    ]
    if student.get("note"):
        parts.append(student["note"])
    if student.get("absences", 0) > 0:
        parts.append(f"이번 달 결석은 {student['absences']}회입니다.")
    parts.append(f"가정에서는 {student['home_tip']}")
    parts.append("궁금하신 점은 언제든 학원으로 연락 주세요.")
    return " ".join(parts)
