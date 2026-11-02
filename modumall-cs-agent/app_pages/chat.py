import json

import streamlit as st

import config
from web.store import get_app, get_inbox

SUGGESTIONS = {
    ":material/local_shipping: 배송 조회": "MD-1001 주문 언제 도착하나요?",
    ":material/payments: 배송비": "배송비 얼마예요? 4만원 정도 살 건데요",
    ":material/assignment_return: 반품": "옷이 마음에 안 들어서 반품하려고요. 배송비 얼마 내야 해요?",
    ":material/inventory_2: 세트 상품": "MD-1002 세트에서 바구니 하나만 반품하고 싶어요",
    ":material/support_agent: 기타 문의": "택배 기사님이 너무 불친절했어요. 보상해 주세요",
}

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.container(horizontal=True, vertical_alignment="center"):
    st.caption("연습용 가상 쇼핑몰입니다. 주문번호 MD-1001, MD-1002, MD-1003으로 시험해 보세요. "
               "질문마다 따로 처리합니다.", width="stretch")
    if st.button("대화 지우기", icon=":material/delete_sweep:"):
        st.session_state.messages = []
        st.rerun()


def show_trace(result: dict) -> None:
    """에이전트가 어떻게 판단했는지: 분류 → 근거·조회 → 숫자 검사."""
    label = config.ROUTE_LABELS.get(result["route"], result["route"])
    with st.expander(f"판단 근거 · {label} · 확신도 {result['confidence']:.2f}", type="compact"):
        with st.status(f"분류: {label}", type="step", state="complete"):
            st.write(result.get("route_reason", ""))
            manual = config.ROUTE_MANUALS.get(result["route"])
            st.caption(f"프롬프트에 넣은 근거 문서: {manual or '없음 (상담원에게 이관)'}")
        tool_results = result.get("sources", [])[2:]  # 앞 2개는 매뉴얼·질문
        if tool_results:
            with st.status(f"조회: 도구 {len(tool_results)}회", type="step", state="complete"):
                for text in tool_results:
                    st.json(json.loads(text), expanded=False)
        if "guard_ok" in result:
            if result["guard_ok"]:
                with st.status("숫자 검사: 통과", type="step", state="complete"):
                    st.write("답변의 숫자가 모두 매뉴얼·조회 결과·질문에 있습니다.")
            else:
                with st.status("숫자 검사: 실패", type="step", state="error"):
                    st.write(f"출처 없는 숫자: {result.get('unsupported_numbers')}")


def show_reply(result: dict) -> None:
    st.markdown(result["answer"])
    if result.get("escalated"):
        st.warning(result.get("escalate_reason", ""), title="상담원에게 넘겼습니다", icon=":material/forward_to_inbox:")
    show_trace(result)


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            show_reply(msg["result"])

prompt = st.chat_input("고객 문의를 입력하세요", submit_mode="disable")

if not st.session_state.messages:
    suggestions = st.empty()
    picked = suggestions.pills("예시 문의", list(SUGGESTIONS), label_visibility="collapsed")
    if picked:
        prompt = SUGGESTIONS[picked]
    if prompt:
        suggestions.empty()

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("답변을 만들고 있어요"):
            result = get_app().invoke({"question": prompt})
        if result.get("escalated"):
            get_inbox().add(result)
        show_reply(result)

    st.session_state.messages.append({"role": "assistant", "result": result})
