"""웹 화면이 함께 쓰는 자원: 그래프, 상담원 확인함.

@st.cache_resource라서 서버 프로세스 하나에 하나만 생긴다. 고객 상담 화면에서 넘긴 문의를
상담원 확인함 화면에서 볼 수 있는 이유다. 과제용이라 서버를 다시 켜면 비워진다.
"""
import threading
from dataclasses import dataclass, field
from datetime import datetime

import streamlit as st

from graph import build_graph


@dataclass
class Escalation:
    id: int
    at: str
    question: str
    route: str
    confidence: float
    reason: str
    draft: str
    done: bool = False


@dataclass
class Inbox:
    items: list[Escalation] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, result: dict) -> None:
        with self.lock:
            self.items.append(Escalation(
                id=len(self.items) + 1, at=datetime.now().strftime("%m-%d %H:%M"),
                question=result["question"], route=result["route"], confidence=result["confidence"],
                reason=result.get("escalate_reason", ""), draft=result.get("draft_answer", ""),
            ))


@st.cache_resource
def get_app():
    return build_graph("llm")


@st.cache_resource
def get_inbox() -> Inbox:
    return Inbox()
