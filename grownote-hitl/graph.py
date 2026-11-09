"""GrowNote 발송 승인 파이프라인 (LangGraph HITL).

compose → check ─(기준 통과)→ send            : 자동 발송
                 └(기준 걸림)→ review ⏸ interrupt
                                 ├ approve → send   : 원장 승인 후 발송
                                 ├ edit    → check  : 고친 문장을 다시 검사
                                 └ reject  → discard: 발송하지 않음
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from compose import compose_draft
from rules import check_message


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class State(TypedDict, total=False):
    student: dict
    roster: list[str]
    draft: str
    hits: list[dict]
    decisions: list[dict]
    status: str  # auto_sent | approved_sent | rejected


class Outbox:
    """발송함. 실제 문자는 보내지 않고 JSON 파일에 쌓는다.
    같은 thread_id는 한 번만 기록한다(재실행해도 중복 발송 없음)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def all(self) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def put(self, key: str, record: dict) -> bool:
        with self._lock:
            rows = self.all()
            if any(r["key"] == key for r in rows):
                return False
            rows.append({"key": key, **record})
            self.path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            return True


def build_graph(outbox: Outbox, checkpointer):
    def compose(state: State):
        return {"draft": compose_draft(state["student"]), "decisions": []}

    def check(state: State):
        return {"hits": check_message(state["draft"], state["student"], state["roster"])}

    def after_check(state: State):
        return "review" if state["hits"] else "send"

    def review(state: State):
        answer = interrupt({
            "student": state["student"]["name"],
            "draft": state["draft"],
            "hits": state["hits"],
        })
        action = answer.get("action")
        if action not in ("approve", "edit", "reject"):
            raise ValueError(f"알 수 없는 결정: {action!r}")
        if action == "edit" and not answer.get("text", "").strip():
            raise ValueError("수정 후 승인에는 고친 문장이 필요합니다")
        decision = {
            "action": action,
            "by": answer.get("by", "원장"),
            "at": now(),
            "rules": sorted({h["rule"] for h in state["hits"]}),
            "memo": answer.get("memo", ""),
        }
        update = {"decisions": state.get("decisions", []) + [decision]}
        if action == "edit":
            update["draft"] = answer["text"].strip()
        return update

    def after_review(state: State):
        return {"approve": "send", "edit": "check", "reject": "discard"}[state["decisions"][-1]["action"]]

    def send(state: State, config):
        status = "approved_sent" if state.get("decisions") else "auto_sent"
        outbox.put(config["configurable"]["thread_id"], {
            "student": state["student"]["name"],
            "status": status,
            "text": state["draft"],
            "decisions": state.get("decisions", []),
            "at": now(),
        })
        return {"status": status}

    def discard(state: State, config):
        outbox.put(config["configurable"]["thread_id"], {
            "student": state["student"]["name"],
            "status": "rejected",
            "text": state["draft"],
            "decisions": state.get("decisions", []),
            "at": now(),
        })
        return {"status": "rejected"}

    g = StateGraph(State)
    for name, fn in [("compose", compose), ("check", check), ("review", review), ("send", send), ("discard", discard)]:
        g.add_node(name, fn)
    g.add_edge(START, "compose")
    g.add_edge("compose", "check")
    g.add_conditional_edges("check", after_check, ["review", "send"])
    g.add_conditional_edges("review", after_review, ["send", "check", "discard"])
    g.add_edge("send", END)
    g.add_edge("discard", END)
    return g.compile(checkpointer=checkpointer)


class Pipeline:
    """일괄 실행 · 대기 목록 · 재개를 묶은 진입점 (웹 화면과 데모 스크립트가 함께 사용)."""

    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.dir / "checkpoints.sqlite", check_same_thread=False)
        self.outbox = Outbox(self.dir / "outbox.json")
        self.graph = build_graph(self.outbox, SqliteSaver(self.conn))
        self.runs_path = self.dir / "runs.json"
        if not self.runs_path.exists():
            self.runs_path.write_text("[]", encoding="utf-8")

    def _runs(self) -> list[dict]:
        return json.loads(self.runs_path.read_text(encoding="utf-8"))

    @staticmethod
    def _cfg(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def run_batch(self, students: list[dict]) -> dict:
        run_id = datetime.now().strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        roster = [s["name"] for s in students]
        threads = []
        for s in students:
            tid = f"{run_id}:{s['id']}"
            self.graph.invoke({"student": s, "roster": roster}, self._cfg(tid))
            threads.append(tid)
        runs = self._runs()
        runs.append({"run_id": run_id, "at": now(), "threads": threads})
        self.runs_path.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"run_id": run_id, **self.summary(threads)}

    def summary(self, threads: list[str]) -> dict:
        counts = {"auto_sent": 0, "approved_sent": 0, "rejected": 0, "pending": 0}
        for tid in threads:
            st = self.graph.get_state(self._cfg(tid))
            counts["pending" if st.next else st.values.get("status", "pending")] += 1
        return counts

    def pending(self) -> list[dict]:
        out = []
        for run in self._runs():
            for tid in run["threads"]:
                st = self.graph.get_state(self._cfg(tid))
                if st.interrupts:
                    out.append({"thread_id": tid, "run_id": run["run_id"], **st.interrupts[0].value})
        return out

    def resume(self, thread_id: str, answer: dict) -> dict:
        self.graph.invoke(Command(resume=answer), self._cfg(thread_id))
        st = self.graph.get_state(self._cfg(thread_id))
        return {"status": "pending" if st.next else st.values.get("status"), "hits": st.values.get("hits", [])}

    def runs(self) -> list[dict]:
        return [{**r, **self.summary(r["threads"])} for r in self._runs()]
