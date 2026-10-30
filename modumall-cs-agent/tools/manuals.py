"""라우트별 업무 매뉴얼 로더. 답변에는 해당 라우트의 매뉴얼만 넣는다(1강: 관련 없는 정책 혼입 방지)."""
import config


def load_manual(route: str) -> str:
    path = config.MANUAL_DIR / f"{route}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""
