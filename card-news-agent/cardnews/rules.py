"""카드 글 규칙: 짧은 글 · 프로그램 내부는 공개하지 않기.

2026-10-23 gangsa-hours 카드뉴스에서 사용자가 직접 고친 두 가지를 앱의 기본 규칙으로 옮겼다(DECISIONS.md).
엔진 요청문(스토리보드·글 고치기)과 화면 검사가 같은 규칙을 쓴다. 검사는 막지 않고 ⚠로 알린다.
"""

TITLE_MAX = 20
KEYLINE_MAX = 40
BODY_MAX = 60

# 독자(사장님)에게는 필요 없고, 공개하면 보안·운영 정보가 드러나는 말
INTERNAL_WORDS = (
    "비밀번호", "로그인", "뒷자리", "뒤 4자리", "뒷 4자리", "체험번호", "자동 저장", "저장 버튼",
    "localStorage", "브라우저에 저장", "서버", "데이터베이스", "Firebase", "Firestore", "API",
    "코드", "수식", "CSV", ".html", ".py", ".js",
)

WRITING_RULES = f"""
글 규칙 (사용자가 정한 기본값):
- 독자는 소비자(사장님)다. 휴대폰에서 3초 안에 읽히게 짧게: 제목 {TITLE_MAX}자 이내, 핵심 문장 한 줄({KEYLINE_MAX}자 이내),
  본문은 비워 두거나 한 문장({BODY_MAX}자 이내). 출처는 마지막 카드 본문에 "자료: …" 한 줄로.
- 프로그램이 어떻게 만들어졌는지는 쓰지 않는다: 로그인 방식·비밀번호·전화번호 자리·체험번호·저장 방식·서버·계산 수식·코드·파일 이름.
  독자가 얻는 변화(무엇이 줄고 무엇이 쉬워지는지)만 쓴다. 편집 방향에서 사용자가 공개하라고 한 것은 예외.
""".strip()


def text_warnings(text, allow=""):
    """카드 글(title/keyLine/body)이 규칙을 어긴 곳. allow(편집 방향)에 적힌 말은 공개를 허락한 것으로 본다."""
    out = []
    limits = (("title", "제목", TITLE_MAX), ("keyLine", "핵심 문장", KEYLINE_MAX), ("body", "본문", BODY_MAX))
    for key, label, limit in limits:
        n = len((text.get(key) or "").strip())
        if n > limit:
            out.append(f"{label}이 깁니다({n}자 > {limit}자)")
    joined = " ".join(text.get(k) or "" for k in ("title", "keyLine", "body"))
    found = [w for w in INTERNAL_WORDS if w.lower() in joined.lower() and w.lower() not in (allow or "").lower()]
    if found:
        out.append("프로그램 내부 내용으로 보이는 말: " + ", ".join(found))
    return out
