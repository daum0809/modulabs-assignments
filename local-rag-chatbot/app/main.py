"""로컬 RAG 챗봇 웹 서버.

실행: uvicorn app.main:app --port 8000
"""
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from . import chat, ollama, rag, store  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("rag")

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 20 * 1024 * 1024

app = FastAPI(title="Local RAG Chatbot")


@app.on_event("startup")
def startup():
    store.init()
    log.info("답변 모델: %s / 임베딩 모델: %s", chat.MODEL, rag.EMBED_MODEL or "(사용 안 함)")
    for model in filter(None, [chat.MODEL, rag.EMBED_MODEL]):
        try:
            if not ollama.has_model(model):
                log.warning("Ollama에 '%s' 모델이 없습니다: ollama pull %s", model, model)
        except ollama.OllamaError as e:
            log.warning("%s (설치: https://ollama.com)", e)
            break
    rag.index.rebuild()


class ChatIn(BaseModel):
    message: str
    history: list[dict] = []


@app.post("/api/chat")
def chat_api(body: ChatIn):
    if not body.message.strip():
        raise HTTPException(400, "질문을 입력하세요.")
    try:
        return chat.answer(body.message.strip()[:4000], body.history)
    except chat.ChatError as e:
        raise HTTPException(502, str(e))


@app.get("/api/documents")
def documents():
    return store.list_documents()


@app.post("/api/documents")
async def upload(file: UploadFile = File(...), title: str = Form("")):
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(400, "파일이 너무 큽니다. (최대 20MB)")
    try:
        text = rag.extract_text(file.filename or "", data)
        doc_id = rag.ingest(title.strip() or Path(file.filename or "문서").stem, text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": doc_id}


@app.delete("/api/documents/{doc_id}")
def delete(doc_id: int):
    store.delete_document(doc_id)
    rag.index.rebuild()
    return {"ok": True}


@app.get("/api/search")
def search(q: str, k: int = 5):
    """검색 단계만 따로 확인하는 디버그용 API."""
    return rag.index.search(q, k=k)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
