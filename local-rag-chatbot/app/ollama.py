"""로컬 Ollama 서버 HTTP 클라이언트 (추가 패키지 없이 urllib 사용).

Ollama 설치: https://ollama.com  →  ollama pull qwen3:8b  /  ollama pull bge-m3
"""
import json
import os
import urllib.error
import urllib.request

URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")


class OllamaError(Exception):
    pass


def post(path: str, body: dict, timeout: float = 300) -> dict:
    req = urllib.request.Request(f"{URL}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", "")
        except Exception:
            msg = ""
        raise OllamaError(msg or f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise OllamaError(f"Ollama 서버({URL})에 연결하지 못했습니다. Ollama가 실행 중인지 확인하세요.") from e


def installed_models() -> list[str]:
    req = urllib.request.Request(f"{URL}/api/tags")
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return [m["name"] for m in json.loads(res.read()).get("models", [])]
    except Exception as e:
        raise OllamaError(f"Ollama 서버({URL})에 연결하지 못했습니다.") from e


def has_model(name: str) -> bool:
    models = installed_models()
    # "bge-m3" 는 "bge-m3:latest" 로 등록된다
    return any(m == name or m == f"{name}:latest" for m in models)


def embed(model: str, texts: list[str], batch: int = 32) -> list[list[float]]:
    out = []
    for i in range(0, len(texts), batch):
        out.extend(post("/api/embed", {"model": model, "input": texts[i:i + batch]})["embeddings"])
    return out
