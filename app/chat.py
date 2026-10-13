"""검색 결과를 근거로 로컬 LLM(Ollama)이 답변을 만든다."""
import os
import re

from . import ollama, rag

MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
TOP_K = int(os.getenv("TOP_K", "5"))

SYSTEM_PROMPT = """너는 등록된 문서를 근거로 답하는 한국어 도우미다.

- 질문과 함께 <context> 안에 검색된 문서 조각이 주어진다. 그 내용에 근거해 답한다.
- 문서에 없는 사실(날짜, 금액, 규정 등)은 지어내지 말고 "등록된 문서에서 찾지 못했습니다"라고 답한다.
- 문서를 근거로 답했다면 문장 끝에 [문서 제목] 형태로 출처를 붙인다.
- 핵심부터 간결하게 답한다."""

_THINK = re.compile(r"<think>.*?</think>", re.S)


class ChatError(Exception):
    pass


def format_context(hits) -> str:
    if not hits:
        return "(검색 결과 없음)"
    return "\n\n".join(f'<doc title="{h["title"]}">\n{h["text"]}\n</doc>' for h in hits)


def answer(question: str, history: list[dict] | None = None) -> dict:
    hits = rag.index.search(question, k=TOP_K)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    # 이전 대화는 최근 몇 턴만 (로컬 모델의 문맥 길이가 짧으므로)
    for h in (history or [])[-6:]:
        if h.get("role") in ("user", "assistant") and isinstance(h.get("content"), str):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": f"<context>\n{format_context(hits)}\n</context>\n\n질문: {question}"})

    body = {"model": MODEL, "messages": messages, "stream": False,
            "options": {"num_ctx": NUM_CTX, "temperature": 0.2},
            "think": False}  # qwen3 등 추론 모델의 '생각' 출력을 끈다
    try:
        res = ollama.post("/api/chat", body)
    except ollama.OllamaError as e:
        if "think" in str(e):  # think 옵션을 모르는 모델/버전
            body.pop("think")
            res = ollama.post("/api/chat", body)
        elif "not found" in str(e):
            raise ChatError(f"Ollama에 '{MODEL}' 모델이 없습니다. 'ollama pull {MODEL}'을 실행하세요.") from e
        else:
            raise ChatError(str(e)) from e

    text = _THINK.sub("", res.get("message", {}).get("content") or "").strip()
    titles = []
    plain = text.replace(" ", "").replace("_", "")  # 모델이 '학원_운영_규정'을 '학원 운영 규정'으로 쓰기도 한다
    for h in hits:
        if h["title"].replace("_", "") in plain and h["title"] not in titles:
            titles.append(h["title"])
    return {"answer": text or "답변을 만들지 못했습니다.", "sources": titles,
            "retrieved": [{"title": h["title"], "score": h["score"], "preview": h["text"][:120]} for h in hits]}
