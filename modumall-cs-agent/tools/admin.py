"""5강: 어드민 시스템 조회 도구 (지금은 data/admin_db.json을 읽는 가짜 구현).

LLM이 스키마를 읽으므로 docstring과 타입 힌트가 곧 도구 설명이다.
"""
import json
from functools import lru_cache

import config


@lru_cache
def _db() -> dict:
    return json.loads(config.ADMIN_DB_PATH.read_text(encoding="utf-8"))


def get_order(order_id: str) -> dict:
    """고객이 알려준 주문번호('MD-'로 시작)로 주문 상태, 상품, 결제 금액, 배송비, 송장번호를 조회한다.

    고객이 주문번호를 말하지 않았으면 호출하지 않는다.
    """
    order = _db()["orders"].get(order_id.strip().upper())
    if order is None:
        return {"error": f"주문 {order_id}을(를) 찾을 수 없습니다."}
    return {"order_id": order_id, **order}


def get_shipping_fee(order_total: int, region: str) -> dict:
    """주문 금액(원)과 배송 지역으로 배송비를 계산한다. 정책은 배송 매뉴얼과 같다."""
    base = 0 if order_total >= 50000 else 3000
    extra = 3000 if region in ("제주", "도서산간") else 0
    return {"order_total": order_total, "region": region, "base_fee": base, "extra_fee": extra, "shipping_fee": base + extra}


# 라우트마다 쓸 수 있는 도구만 넘긴다
ROUTE_TOOLS = {
    "delivery": [get_order, get_shipping_fee],
    "return": [get_order],
    "bundle": [get_order],
    "order": [get_order],
}
