import streamlit as st

import config
from web.store import get_inbox

inbox = get_inbox()
pending = [e for e in inbox.items if not e.done]
done = [e for e in inbox.items if e.done]

with st.container(horizontal=True):
    st.metric("확인 대기", len(pending), border=True)
    st.metric("처리 완료", len(done), border=True)

view = st.segmented_control("보기", ["확인 대기", "처리 완료"], default="확인 대기", label_visibility="collapsed")
items = pending if view == "확인 대기" else done

if not items:
    st.info("고객 상담 화면에서 상담원에게 넘어온 문의가 여기에 쌓입니다. 서버를 다시 켜면 비워집니다.",
            icon=":material/inbox:")

for e in reversed(items):
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"**#{e.id}** · {e.at}")
            st.badge(config.ROUTE_LABELS.get(e.route, e.route), color="blue")
            st.badge(f"확신도 {e.confidence:.2f}", color="gray")
        st.markdown(f"> {e.question}")
        st.caption(f"넘긴 이유: {e.reason}")
        if e.draft:
            with st.expander("에이전트가 쓴 초안 (고객에게는 보내지 않음)"):
                st.markdown(e.draft)
        if not e.done and st.button("처리 완료", key=f"done-{e.id}", icon=":material/check:"):
            e.done = True
            st.rerun()
