"""라우트별 업무 매뉴얼 로더. 답변에는 해당 라우트의 매뉴얼만 넣는다(1강: 관련 없는 정책 혼입 방지)."""
import config


def load_manual(route: str) -> str:
    """config.ROUTE_MANUALS에 매핑된 근거 문서 하나만 돌려준다. 매핑이 없으면 빈 문자열."""
    name = config.ROUTE_MANUALS.get(route)
    if not name:
        return ""
    return (config.MANUAL_DIR / name).read_text(encoding="utf-8")
