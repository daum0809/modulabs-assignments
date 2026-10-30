"""그래프 전체가 공유하는 State."""
from typing import TypedDict


class AgentState(TypedDict, total=False):
    question: str

    # route
    route: str
    confidence: float
    route_reason: str

    # answer
    answer: str
    sources: list[str]  # 매뉴얼 원문 + 도구 반환값. guard가 숫자 출처를 찾는 곳

    # guard
    guard_ok: bool
    unsupported_numbers: list[str]

    # escalate
    escalated: bool
    escalate_reason: str
    draft_answer: str  # 이관 전 모델이 만든 답변 (상담원 참고용)
