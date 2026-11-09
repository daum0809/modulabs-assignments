"""GrowNote 발송 승인실 — Streamlit 웹 데모.

실행: streamlit run app.py
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path

import streamlit as st

from graph import Pipeline
from rules import RULES

BASE = Path(__file__).parent
DATA_DIR = Path(os.environ.get("GROWNOTE_DATA_DIR", BASE / "data" / "runtime"))
STUDENTS = json.loads((BASE / "data" / "students.json").read_text(encoding="utf-8"))
STATUS_LABEL = {"auto_sent": "🟢 자동 발송", "approved_sent": "🔵 승인 후 발송", "rejected": "⛔ 반려"}

st.set_page_config(page_title="GrowNote 발송 승인실", page_icon="📨", layout="wide")


@st.cache_resource
def get_pipeline(data_dir: str) -> Pipeline:
    return Pipeline(Path(data_dir))


pipe = get_pipeline(str(DATA_DIR))


def highlight(text: str, hits: list[dict]) -> str:
    out = html.escape(text)
    for m in sorted({h["match"] for h in hits}, key=len, reverse=True):
        esc = html.escape(m)
        out = out.replace(esc, f"<mark style='background:#ffd6d6;color:#9b1c1c;padding:0 2px'>{esc}</mark>")
    return f"<div style='line-height:1.7'>{out}</div>"


st.title("📨 GrowNote 발송 승인실")
st.caption("AI가 쓴 학부모 피드백 문자를 내보내기 직전에 검사합니다. 승인 기준에 걸린 문자만 원장님 승인을 기다리고, 나머지는 자동 발송됩니다. (실제 문자는 보내지 않고 발송함에 기록합니다. 학생 데이터는 모두 가상입니다.)")

pending = pipe.pending()
t1, t2, t3, t4 = st.tabs(["① 일괄 실행", f"② 승인 대기함 ({len(pending)})", "③ 발송함·기록", "승인 기준"])

with t1:
    st.subheader("오늘 수업 기록 → 학부모 문자 만들기")
    st.dataframe(
        [{"학생": s["name"], "단원": s["unit"], "강사 메모": s["note"] or "—",
          "이전 발송": s["history_count"], "이번 달 결석": s["absences"]} for s in STUDENTS],
        hide_index=True, use_container_width=True,
    )
    if st.button(f"피드백 문자 만들기 ({len(STUDENTS)}명)", type="primary", key="run"):
        res = pipe.run_batch(STUDENTS)
        st.session_state["last_run"] = res
        st.rerun()
    if res := st.session_state.get("last_run"):
        st.success(f"실행 {res['run_id']} 완료")
        c1, c2, c3 = st.columns(3)
        c1.metric("자동 발송", res["auto_sent"])
        c2.metric("승인 대기", res["pending"])
        c3.metric("전체", res["auto_sent"] + res["pending"] + res["approved_sent"] + res["rejected"])
        if res["pending"]:
            st.info("② 승인 대기함 탭에서 걸린 문자를 확인하세요.")

with t2:
    if not pending:
        st.success("승인 대기 중인 문자가 없습니다.")
    for item in pending:
        tid = item["thread_id"]
        with st.container(border=True):
            st.markdown(f"#### {item['student']}  <span style='color:gray;font-size:0.8em'>실행 {item['run_id']}</span>", unsafe_allow_html=True)
            for h in item["hits"]:
                st.markdown(f"- **{h['rule']} {RULES[h['rule']]['title']}** — {h['detail']} (`{h['match']}`)")
            st.markdown(highlight(item["draft"], item["hits"]), unsafe_allow_html=True)
            edited = st.text_area("고쳐서 보내려면 여기서 수정", item["draft"], key=f"txt-{tid}", height=120)
            b1, b2, b3 = st.columns(3)
            if b1.button("✅ 그대로 승인", key=f"ok-{tid}"):
                r = pipe.resume(tid, {"action": "approve"})
                st.toast(f"{item['student']}: 승인 후 발송")
                st.rerun()
            if b2.button("✏️ 수정 후 승인", key=f"ed-{tid}"):
                r = pipe.resume(tid, {"action": "edit", "text": edited})
                if r["status"] == "pending":
                    st.session_state["flash"] = f"{item['student']}: 고친 문장에 아직 기준에 걸리는 내용이 있어 대기함에 남았습니다."
                else:
                    st.toast(f"{item['student']}: 다시 검사 통과 → 발송")
                st.rerun()
            if b3.button("⛔ 반려", key=f"rj-{tid}"):
                pipe.resume(tid, {"action": "reject"})
                st.toast(f"{item['student']}: 반려 (발송 안 함)")
                st.rerun()
    if msg := st.session_state.pop("flash", None):
        st.warning(msg)

with t3:
    rows = list(reversed(pipe.outbox.all()))
    st.subheader(f"발송함 ({len(rows)}건)")
    st.dataframe(
        [{"시각": r["at"], "학생": r["student"], "처리": STATUS_LABEL[r["status"]],
          "결정": " → ".join(f"{d['action']}({','.join(d['rules'])})" for d in r["decisions"]) or "—",
          "본문": r["text"]} for r in rows],
        hide_index=True, use_container_width=True,
    )
    st.subheader("실행 기록")
    st.dataframe(
        [{"실행": r["run_id"], "시각": r["at"], "자동 발송": r["auto_sent"], "승인 후 발송": r["approved_sent"],
          "반려": r["rejected"], "대기": r["pending"]} for r in reversed(pipe.runs())],
        hide_index=True, use_container_width=True,
    )

with t4:
    st.subheader("승인 기준 (모두 코드로 계산, AI 판단 없음)")
    st.dataframe(
        [{"기준": k, "이름": v["title"], "계산 방법": v["how"], "막으려는 위험": v["risk"]} for k, v in RULES.items()],
        hide_index=True, use_container_width=True,
    )
    st.markdown("하나라도 걸리면 ⏸ 대기, 하나도 안 걸리면 자동 발송. **수정 후 승인**한 문장은 같은 기준으로 다시 검사합니다.")
