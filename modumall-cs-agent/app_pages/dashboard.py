"""평가 대시보드: eval/score_pipeline.py가 저장한 결과(eval/results/*.jsonl)를 보여 준다.

결과를 새로 만들려면: python -m eval.score_pipeline --router llm --set test (API 요금 발생)
"""
import json
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import config
from eval.answer_rubric import CRITERIA
from eval.metrics import accuracy, macro_f1

RESULTS_DIR = Path(config.ROOT) / "eval" / "results"
SETS = {"테스트셋 (튜닝에 안 쓴 12문항)": "test", "개발셋 (튜닝하며 본 14문항)": "dev"}


@st.cache_data
def load_results(path: str, mtime: float) -> list[dict]:  # mtime: 파일이 바뀌면 다시 읽는다
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


picked = st.segmented_control("평가셋", list(SETS), default=list(SETS)[0], label_visibility="collapsed")
path = RESULTS_DIR / f"{SETS[picked or list(SETS)[0]]}.jsonl"
if not path.exists():
    st.info(f"아직 채점 결과가 없습니다. `python -m eval.score_pipeline --router llm --set {SETS[picked]}`를 실행하세요.",
            icon=":material/info:")
    st.stop()

rows = load_results(str(path), path.stat().st_mtime)
st.caption(f"채점 시각 {datetime.fromtimestamp(path.stat().st_mtime):%Y-%m-%d %H:%M} · LLM 라우터 · "
           f"새로 채점: `python -m eval.score_pipeline --router llm --set {SETS[picked]}`")

y_true = [r["expected_route"] for r in rows]
y_pred = [r["route"] for r in rows]
f1, per_label = macro_f1(y_true, y_pred)
n = len(rows)
passed_all = sum(r["blame"] is None for r in rows)
escalate_ok = sum(r["escalated"] == r["expected_escalate"] for r in rows)

# ---------- KPI ----------
with st.container(horizontal=True):
    st.metric("전체 통과", f"{passed_all}/{n}", border=True, help="R1~R5 기준을 모두 통과한 문항")
    st.metric("분류 정확도", f"{accuracy(y_true, y_pred):.3f}", border=True)
    st.metric("Macro F1", f"{f1:.3f}", border=True)
    st.metric("이관 판정 일치", f"{escalate_ok}/{n}", border=True, help="사람에게 넘길지 판단이 정답과 같은 문항")

# ---------- 기준별 통과율 / 카테고리별 성능 ----------
left, right = st.columns(2)
with left, st.container(border=True, height="stretch"):
    st.markdown("**답변 품질 기준별 통과율**")
    crit = []
    for key, desc in CRITERIA.items():
        applicable = [r["grades"][key] for r in rows if r["grades"][key] is not None]
        crit.append({"기준": key, "통과율": sum(applicable) / len(applicable) if applicable else None,
                     "통과": f"{sum(applicable)}/{len(applicable)}", "설명": desc})
    crit_df = pd.DataFrame(crit)
    bars = alt.Chart(crit_df).mark_bar().encode(
        x=alt.X("통과율:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%")),
        y=alt.Y("기준:N", sort=None, title=None),
        tooltip=["기준", "통과", "설명"],
    )
    labels = bars.mark_text(align="left", dx=4).encode(text="통과:N")
    st.altair_chart(bars + labels, alt="답변 품질 기준별 통과율")
    st.caption("이관된 문항은 고객에게 안내 문구만 나가므로 R3~R5에서 제외합니다.")

with right, st.container(border=True, height="stretch"):
    st.markdown("**카테고리별 분류 성능**")
    st.dataframe(
        pd.DataFrame([{"카테고리": f"{k} ({config.ROUTE_LABELS[k]})", "정밀도": m["precision"], "재현율": m["recall"],
                       "F1": m["f1"], "문항 수": m["support"]} for k, m in per_label.items()]),
        hide_index=True,
        column_config={c: st.column_config.NumberColumn(format="%.2f") for c in ("정밀도", "재현율", "F1")},
        alt="카테고리별 정밀도, 재현율, F1",
    )

# ---------- 혼동 행렬 ----------
with st.container(border=True):
    st.markdown("**혼동 행렬** (세로: 정답, 가로: 예측)")
    cells = [{"정답": t, "예측": p, "문항 수": sum(a == t and b == p for a, b in zip(y_true, y_pred))}
             for t in config.ROUTES for p in config.ROUTES]
    cm = pd.DataFrame(cells)
    base = alt.Chart(cm).encode(x=alt.X("예측:N", sort=list(config.ROUTES)), y=alt.Y("정답:N", sort=list(config.ROUTES)))
    heat = base.mark_rect().encode(color=alt.Color("문항 수:Q", scale=alt.Scale(scheme="blues"), legend=None),
                                   tooltip=["정답", "예측", "문항 수"])
    text = base.mark_text(fontSize=16).encode(
        text="문항 수:Q", color=alt.condition("datum['문항 수'] > 1", alt.value("white"), alt.value("#1a1a1a")))
    st.altair_chart((heat + text).properties(height=260), alt="카테고리 혼동 행렬")

# ---------- 실패 문항 ----------
failures = [r for r in rows if r["blame"]]
st.subheader(f"실패 문항 {len(failures)}건", anchor=False)
if not failures:
    st.success("모든 문항이 기준을 통과했습니다. 통과한 답변도 아래 전체 표에서 직접 읽어 보세요.",
               icon=":material/check_circle:")
for r in failures:
    failed = [k for k, v in r["grades"].items() if v is False]
    with st.expander(f"{r['id']} · {r['text']}  —  원인: {r['blame']}", icon=":material/error:"):
        st.markdown(f"- 정답 카테고리 **{r['expected_route']}** / 예측 **{r['route']}** (확신도 {r['confidence']})\n"
                    f"- 실패 기준: {', '.join(failed)}\n"
                    f"- 이관: {'예' if r['escalated'] else '아니오'} (정답: {'예' if r['expected_escalate'] else '아니오'})"
                    + (f" — {r['escalate_reason']}" if r["escalate_reason"] else ""))
        st.markdown("**고객에게 나간 답변**")
        st.markdown(r["answer"])
        if r["draft_answer"]:
            st.markdown("**에이전트 초안 (이관되어 보내지 않음)**")
            st.markdown(r["draft_answer"])
st.caption("원인별 해석은 실패분석.md에 정리되어 있습니다.")

# ---------- 전체 문항 ----------
with st.expander("전체 문항 답변 보기", icon=":material/table_view:"):
    st.dataframe(
        pd.DataFrame([{"문항": r["id"], "통과": r["blame"] is None, "질문": r["text"], "정답": r["expected_route"],
                       "예측": r["route"], "확신도": r["confidence"], "이관": r["escalated"],
                       "답변": r["draft_answer"] or r["answer"]} for r in rows]),
        hide_index=True,
        column_config={"통과": st.column_config.CheckboxColumn(), "이관": st.column_config.CheckboxColumn(),
                       "확신도": st.column_config.NumberColumn(format="%.2f"),
                       "답변": st.column_config.TextColumn(width="large")},
        alt="전체 문항별 채점 결과와 답변",
    )
