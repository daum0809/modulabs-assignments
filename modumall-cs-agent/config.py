"""프로젝트 전역 설정."""
import os
from pathlib import Path

ROOT = Path(__file__).parent

try:  # .env의 ANTHROPIC_API_KEY 등을 읽는다. 키가 필요 없는 스크립트는 dotenv 없이도 돈다.
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass
DATA_DIR = ROOT / "data"
MANUAL_DIR = DATA_DIR / "manuals"
ADMIN_DB_PATH = DATA_DIR / "admin_db.json"
EVAL_SET_PATH = DATA_DIR / "eval_set.jsonl"

# 2강: 라우트 체계. "other"는 매뉴얼이 없어 항상 사람에게 넘긴다.
ROUTES = ("delivery", "return", "bundle", "order", "other")
ROUTE_LABELS = {
    "delivery": "배송",
    "return": "반품·교환",
    "bundle": "세트 상품",
    "order": "주문·결제",
    "other": "기타",
}

# 4강: 이 값보다 확신도가 낮으면 escalate
CONFIDENCE_THRESHOLD = float(os.getenv("MODUMALL_CONFIDENCE_THRESHOLD", "0.7"))

# LangChain init_chat_model 형식("공급자:모델명")
MODEL = os.getenv("MODUMALL_MODEL", "anthropic:claude-sonnet-5-5")

# 6강: 답변 노드에서 도구 호출을 반복할 최대 횟수
MAX_TOOL_ROUNDS = 3
