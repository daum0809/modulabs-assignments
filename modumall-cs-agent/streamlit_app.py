"""모두몰 고객 응대 에이전트 웹 화면.

실행: streamlit run streamlit_app.py
"""
import streamlit as st

st.set_page_config(page_title="모두몰 고객 응대", page_icon=":material/support_agent:", layout="wide")

page = st.navigation(
    [
        st.Page("app_pages/chat.py", title="고객 상담", icon=":material/chat:"),
        st.Page("app_pages/dashboard.py", title="평가 대시보드", icon=":material/monitoring:"),
        st.Page("app_pages/inbox.py", title="상담원 확인함", icon=":material/inbox:"),
    ],
    position="top",
)
st.title(page.title, anchor=False)
page.run()
