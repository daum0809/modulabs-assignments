"""4강: 구조화된 출력을 쓰는 LLM 라우터."""
from typing import Literal

from pydantic import BaseModel, Field

import config
from llm import get_llm


class RouteDecision(BaseModel):
    route: Literal["delivery", "return", "bundle", "order", "other"]
    confidence: float = Field(ge=0.0, le=1.0, description="이 분류가 맞을 확률(0~1)")
    reason: str = Field(description="분류 근거 한 문장")


SYSTEM_PROMPT = """너는 쇼핑몰 '모두몰'의 고객 문의 분류기다.
문의를 아래 라우트 중 하나로 분류하고 확신도를 0~1로 매긴다.

{route_list}

규칙:
- 세트 상품 관련이면 반품·교환 이야기가 있어도 bundle로 분류한다.
- 배송지·주소 변경, 주문 취소, 결제는 '배송'이라는 말이 있어도 order로 분류한다.
  delivery는 배송 상태·도착일·배송비·배송 가능 지역 문의만 해당한다.
- 여러 유형이 섞였거나 보상·항의처럼 매뉴얼로 답할 수 없는 문의는 확신도를 낮게 준다.
"""


def llm_route(question: str) -> tuple[str, float, str]:
    route_list = "\n".join(f"- {k}: {v}" for k, v in config.ROUTE_LABELS.items())
    router = get_llm().with_structured_output(RouteDecision)
    decision: RouteDecision = router.invoke([
        ("system", SYSTEM_PROMPT.format(route_list=route_list)),
        ("human", question),
    ])
    return decision.route, decision.confidence, decision.reason
