"""8강: route → answer → guard → (END | escalate) 그래프.

실행 예: python graph.py "MD-1001 언제 와요?" --router rule
"""
import argparse
import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph

import config
from guards import check_numbers
from llm import get_llm
from routers import rule_route
from state import AgentState
from tools import ROUTE_TOOLS, load_manual

ANSWER_PROMPT = """너는 쇼핑몰 '모두몰'의 고객 상담원이다. 문의 유형: {label}

아래 업무 매뉴얼과 도구 조회 결과에 있는 내용만으로 답한다.
- 매뉴얼이나 조회 결과에 없는 숫자(금액, 기간, 날짜)는 절대 쓰지 않는다.
- 숫자를 더하거나 곱해 합계를 만들지 않는다. "기본 배송비 3,000원, 추가 배송비 3,000원"처럼 항목별로 안내한다.
- 주문번호가 있으면 먼저 도구로 조회한다.
- 근거가 없어 답할 수 없으면 "확인 후 안내드리겠습니다"라고만 쓴다.

[업무 매뉴얼]
{manual}
"""

ESCALATE_MESSAGE = "문의 주셔서 감사합니다. 담당 상담원이 확인 후 빠르게 답변드리겠습니다."


def _text(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(block.get("text", "") for block in content if isinstance(block, dict))


# ---------- 노드 ----------

def make_route_node(router: str):
    if router == "rule":
        route_fn = rule_route
    else:
        from routers.llm_router import llm_route
        route_fn = llm_route

    def route_node(state: AgentState) -> AgentState:
        route, confidence, reason = route_fn(state["question"])
        return {"route": route, "confidence": confidence, "route_reason": reason}

    return route_node


def answer_node(state: AgentState) -> AgentState:
    route = state["route"]
    manual = load_manual(route)
    tools = [tool(fn) for fn in ROUTE_TOOLS.get(route, [])]
    tools_by_name = {t.name: t for t in tools}
    llm = get_llm().bind_tools(tools) if tools else get_llm()

    messages = [
        SystemMessage(ANSWER_PROMPT.format(label=config.ROUTE_LABELS[route], manual=manual)),
        HumanMessage(state["question"]),
    ]
    sources = [manual, state["question"]]

    for _ in range(config.MAX_TOOL_ROUNDS):
        ai = llm.invoke(messages)
        messages.append(ai)
        if not ai.tool_calls:
            return {"answer": _text(ai), "sources": sources}
        for call in ai.tool_calls:
            result = tools_by_name[call["name"]].invoke(call["args"])
            result_text = json.dumps(result, ensure_ascii=False)
            sources.append(result_text)
            messages.append(ToolMessage(result_text, tool_call_id=call["id"]))

    # 도구 호출만 반복하다 끝난 경우: 빈 답변으로 두면 guard에서 걸러진다
    return {"answer": "", "sources": sources}


def guard_node(state: AgentState) -> AgentState:
    answer = state.get("answer", "")
    if not answer.strip():
        return {"guard_ok": False, "unsupported_numbers": []}
    ok, unsupported = check_numbers(answer, state.get("sources", []))
    return {"guard_ok": ok, "unsupported_numbers": unsupported}


def escalate_node(state: AgentState) -> AgentState:
    if state.get("route") == "other":
        reason = "매뉴얼 범위 밖 문의"
    elif state.get("confidence", 0.0) < config.CONFIDENCE_THRESHOLD:
        reason = f"라우팅 확신도 낮음 ({state.get('confidence')})"
    elif state.get("unsupported_numbers"):
        reason = f"출처 없는 숫자: {state['unsupported_numbers']}"
    else:
        reason = "답변 생성 실패"
    # 사람 상담원 큐에 넣는 자리. 지금은 고객 안내 문구로 답변을 바꾼다.
    return {
        "escalated": True,
        "escalate_reason": reason,
        "draft_answer": state.get("answer", ""),
        "answer": ESCALATE_MESSAGE,
    }


# ---------- 조건부 에지 ----------

def after_route(state: AgentState) -> str:
    if state["route"] == "other" or state["confidence"] < config.CONFIDENCE_THRESHOLD:
        return "escalate"
    return "answer"


def after_guard(state: AgentState) -> str:
    return END if state["guard_ok"] else "escalate"


def build_graph(router: str = "llm"):
    graph = StateGraph(AgentState)
    graph.add_node("route", make_route_node(router))
    graph.add_node("answer", answer_node)
    graph.add_node("guard", guard_node)
    graph.add_node("escalate", escalate_node)

    graph.add_edge(START, "route")
    graph.add_conditional_edges("route", after_route, ["answer", "escalate"])
    graph.add_edge("answer", "guard")
    graph.add_conditional_edges("guard", after_guard, [END, "escalate"])
    graph.add_edge("escalate", END)
    return graph.compile()


def main():
    parser = argparse.ArgumentParser(description="모두몰 고객 응대 에이전트")
    parser.add_argument("question")
    parser.add_argument("--router", choices=["rule", "llm"], default="llm")
    args = parser.parse_args()

    result = build_graph(args.router).invoke({"question": args.question})
    print(f"[route] {result['route']} (확신도 {result['confidence']}) - {result['route_reason']}")
    if result.get("escalated"):
        print(f"[escalate] {result['escalate_reason']}")
    print(f"[answer]\n{result['answer']}")


if __name__ == "__main__":
    main()
