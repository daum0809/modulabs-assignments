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
EVAL_SET_PATH = DATA_DIR / "eval_set.jsonl"  # 개발셋: 프롬프트·규칙을 고칠 때 본 문항
TEST_SET_PATH = DATA_DIR / "test_set.jsonl"  # 테스트셋: 튜닝에 쓰지 않고 최종 점수만 잰 문항

# 2강: 라우트 체계. "other"는 어디에도 속하지 않는 문의를 담고, 근거 문서가 없어 항상 사람에게 넘긴다.
ROUTES = ("delivery", "return", "bundle", "order", "other")
ROUTE_LABELS = {
    "delivery": "배송",
    "return": "반품·교환",
    "bundle": "세트 상품",
    "order": "주문·결제",
    "other": "기타",
}

# 카테고리 → 근거 문서 매핑. 답변 프롬프트에는 이 문서 하나만 들어간다 (다른 정책 혼입 방지).
# 조회 도구 매핑은 tools/admin.py의 ROUTE_TOOLS.
ROUTE_MANUALS = {
    "delivery": "delivery.md",  # 배송비, 무료배송 기준, 도서산간 추가비, 출고 기간, 배송 조회
    "return": "return.md",      # 반품·교환 기간, 단순변심/불량 배송비, 환불 시점
    "bundle": "bundle.md",      # 세트 부분 반품 불가, 구성품 불량 교환, 세트 할인
    "order": "order.md",        # 출고 전 취소, 출고 후 반품 전환, 카드 취소 반영, 배송지 변경
    "other": None,              # 근거 문서 없음 → 답변 노드로 가지 않고 escalate
}

# 4강: 이 값보다 확신도가 낮으면 escalate
CONFIDENCE_THRESHOLD = float(os.getenv("MODUMALL_CONFIDENCE_THRESHOLD", "0.7"))

# LangChain init_chat_model 형식("공급자:모델명")
MODEL = os.getenv("MODUMALL_MODEL", "anthropic:claude-sonnet-5-5")

# 6강: 답변 노드에서 도구 호출을 반복할 최대 횟수
MAX_TOOL_ROUNDS = 3
