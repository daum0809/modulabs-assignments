"""모의 엔진. 실제 조사를 하지 않고 화면 흐름을 확인하기 위한 예시 자료만 돌려준다.

모든 후보와 문장 앞에 [모의]를 붙여 실제 결과로 오해하지 않게 한다.
"""

import time
import uuid
from datetime import datetime, timedelta

STEP_SECONDS = 0.8


class Cancelled(Exception):
    pass


def _wait(cancel, seconds):
    if cancel.wait(seconds):
        raise Cancelled()


class MockEngine:
    name = "mock"

    def __init__(self, fail=None, step_seconds=STEP_SECONDS):
        # fail: 일부러 실패시킬 작업 이름 집합 (예: {"research"}). 실패 경로 시험용.
        self.fail = set(fail or [])
        self.step_seconds = step_seconds

    def new_session(self):
        return f"mock-{uuid.uuid4().hex[:8]}"

    def research(self, ctx, emit, cancel):
        emit("[모의] 조사를 시작합니다. 실제 검색은 하지 않습니다.")
        _wait(cancel, self.step_seconds)
        if "research" in self.fail:
            return {
                "type": "error",
                "code": "search_failed",
                "message": "[모의 오류] 검색 도구 호출이 실패했습니다.",
            }
        emit("[모의] 예시 후보를 만들었습니다.")
        _wait(cancel, self.step_seconds)

        now = datetime.now().astimezone()
        days = ctx.get("periodDays") or 7
        source = ctx.get("sourcePath")
        candidates = _mock_candidates(source, now)
        # 일부러 7개보다 적게 돌려줘 '기간 넓히기' 안내가 보이게 한다(7일일 때만).
        if days == 7:
            candidates = candidates[:6]
        return {
            "type": "result",
            "sessionId": ctx.get("sessionId"),
            "research": {
                "researchedAt": now.isoformat(timespec="seconds"),
                "timezone": now.tzname() or "",
                "periodStart": (now - timedelta(days=days)).date().isoformat(),
                "periodEnd": now.date().isoformat(),
                "periodDays": days,
                "sourcePath": source,
                "note": "모의 데이터입니다. 실제 조사 결과가 아닙니다.",
                "mock": True,
                "candidates": candidates,
            },
        }

    def _checklist(self, ctx, emit, cancel):
        """모의 체크리스트: 자료 폴더 글자 수가 적으면 자료 부족 질문부터 한다."""
        from pathlib import Path

        answered = {a["key"] for a in ctx.get("answers", [])}
        dirs = [Path(d) for d in [ctx.get("sourcePath"), *(ctx.get("extraSources") or [])] if d]
        files = [f for d in dirs if d.is_dir() for f in d.iterdir() if f.is_file()]
        size = sum(f.stat().st_size for f in files)
        _wait(cancel, self.step_seconds)
        if size < 300 and "material" not in answered:
            return {"type": "need_input", "question": {
                "key": "material", "question": "자료가 부족합니다. 어떻게 할까요?",
                "why": f"[모의] 자료가 {size}바이트뿐이라 근거로 쓸 내용이 거의 없습니다.",
                "options": [{"id": "more", "label": "자료를 더 넣을게요", "desc": "자유 입력에 추가 자료 폴더 경로"},
                            {"id": "as_is", "label": "부족한 대로 만들기", "desc": "근거 없는 칸은 비워 둠"}],
                "recommended": "more", "recommendReason": "[모의] 근거 없이 만들면 대부분 빈칸입니다.", "allowFree": True}}
        name = files[0].name if files else "README.md"
        found = size >= 300
        item = lambda t: {"item": f"[모의] {t}", "basis": f"{name} (예시)" if found else "", "basisFound": found}
        return {"type": "result", "sessionId": ctx.get("sessionId"), "editorial": {"mock": True, "checklist": {
            "title": "[모의] 도입 체크리스트", "target": "[모의] 사장님",
            "prepare": [item("준비물 예시")], "steps": [item("1단계 예시"), item("2단계 예시")], "cautions": [item("주의 예시")],
            "missing": [] if found else ["[모의] 자료가 짧아 준비물·순서를 확인하지 못함"], "note": "[모의] 예시"}}}

    def editorial(self, ctx, emit, cancel):
        if ctx.get("workflow") == "checklist":
            return self._checklist(ctx, emit, cancel)
        answered = {a["key"]: a for a in ctx.get("answers", [])}
        emit("[모의] 선택한 후보를 심층 조사하는 척합니다.")
        _wait(cancel, self.step_seconds)
        if "editorial" in self.fail:
            return {
                "type": "error",
                "code": "engine_error",
                "message": "[모의 오류] 심층 조사 중 엔진이 잘못된 출력을 돌려줬습니다.",
            }

        direction = (ctx.get("direction") or "").strip()
        if "audience" not in answered and not direction:
            emit("[모의] 독자에 따라 카드 구성이 크게 달라져 질문이 필요합니다.")
            return {"type": "need_input", "question": _audience_question()}

        if "format" not in answered:
            audience = answered.get("audience", {}).get("label") or direction
            emit("[모의] 두 형식의 결과가 크게 달라 형식을 묻습니다.")
            return {"type": "need_input", "question": _format_question(audience)}

        emit("[모의] 답변을 반영해 편집 방향을 정리했습니다.")
        _wait(cancel, self.step_seconds)
        audience = answered.get("audience", {}).get("label") or direction
        fmt = answered["format"]["label"]
        return {
            "type": "result",
            "editorial": {
                "mock": True,
                "audience": audience,
                "audienceSource": "사용자 답변" if "audience" in answered else "편집 방향 입력",
                "format": fmt,
                "hooks": [
                    f"[모의] {fmt} 표지 문장 예시 1",
                    f"[모의] {fmt} 표지 문장 예시 2",
                ],
                "note": "모의 데이터입니다. 다음 단계(스토리보드)는 아직 만들지 않았습니다.",
            },
        }


    def storyboard(self, ctx, emit, cancel):
        emit("[모의] 스토리보드를 만듭니다.")
        _wait(cancel, self.step_seconds)
        if "storyboard" in self.fail:
            return {"type": "error", "code": "engine_error", "message": "[모의 오류] 스토리보드를 만들지 못했습니다."}
        fmt = (ctx.get("editorial") or {}).get("format") or "이야기형"
        roles = ["표지", "문제", "바뀐 점", "활용", "한계", "요약·출처"]
        feedback = ctx.get("storyboardFeedback") or []
        cards = []
        for i, role in enumerate(roles, start=1):
            cards.append({
                "no": i, "role": role,
                "title": f"[모의] {role} 카드 제목",
                "keyLine": f"[모의] {role} 카드의 핵심 문장",
                "body": "[모의] 본문 예시입니다. 실제 원고가 아닙니다.",
                "imageRole": f"[모의] {role} 상황을 보여 줌",
                "imagePlan": f"[모의] {role}을 나타내는 단순한 도형",
                "sources": ["[모의] 출처 예시"],
                "note": ("변경 요청 반영: " + feedback[-1]) if feedback and i == 1 else "",
            })
        return {"type": "result", "sessionId": ctx.get("sessionId"), "storyboard": {
            "mock": True, "format": fmt, "reason": "[모의] 6장 예시",
            "style": {"palette": ["#1F3A5F", "#F2C14E", "#F7F7F2", "#E4572E"],
                      "illustration": "[모의] 평면 도형", "mood": "차분함", "layout": "위쪽 40%를 비워 제목 자리"},
            "cards": cards}}

    def revise_text(self, ctx, card, text, instruction, emit, cancel):
        _wait(cancel, self.step_seconds / 2)
        if "revise" in self.fail:
            return {"type": "error", "code": "engine_error", "message": "[모의 오류] 글을 고치지 못했습니다."}
        return {"type": "ok", "text": dict(text, body=f"[모의 수정] {instruction[:40]}"), "note": "[모의] 본문 교체", "cost": 0}

    def draw_svg(self, ctx, card, style, emit, cancel):
        _wait(cancel, self.step_seconds / 2)
        if "image" in self.fail or (card.get("no") == 2 and "image2" in self.fail):
            return {"type": "error", "code": "image_failed", "message": "[모의 오류] 그림을 만들지 못했습니다."}
        pal = style.get("palette") or ["#1F3A5F", "#F2C14E", "#F7F7F2"]
        n = int(card.get("no") or 1)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1350" width="1080" height="1350">'
               f'<rect width="1080" height="1350" fill="{pal[-1]}"/>'
               f'<circle cx="{300 + n * 80}" cy="950" r="{140 + n * 10}" fill="{pal[0]}"/>'
               f'<rect x="560" y="820" width="320" height="320" rx="40" fill="{pal[1 % len(pal)]}"/></svg>')
        return {"type": "ok", "svg": "```svg\n" + svg + "\n```", "cost": 0}


def _mock_candidates(source, now):
    where = "자료 폴더" if source else "웹"
    base = [
        ("반복 업무를 줄인 방법", "문제", "미확인"),
        ("병목이 어디였는지", "발견", (now - timedelta(days=2)).date().isoformat()),
        ("계산 규칙 한 가지", "기능", (now - timedelta(days=3)).date().isoformat()),
        ("화면을 역할별로 나눈 이유", "설계", "미확인"),
        ("저장 방식을 바꾼 이유", "설계", (now - timedelta(days=5)).date().isoformat()),
        ("써 보고 알게 된 한계", "한계", (now - timedelta(days=6)).date().isoformat()),
        ("직접 따라 해 보는 순서", "사용법", "미확인"),
        ("다음에 고칠 점", "계획", "미확인"),
    ]
    out = []
    for i, (title, kind, date) in enumerate(base, start=1):
        out.append(
            {
                "id": f"c{i}",
                "title": f"[모의] 후보 {i}: {title}",
                "summary": f"[모의] {where}에서 찾았다고 가정한 예시 요약입니다.",
                "kind": kind,
                "date": date,
                "source": (f"{source} (예시 경로)" if source else "https://example.com/mock"),
                "value": "[모의] 이 후보를 고를 가치 예시",
                "uncertainty": "[모의] 날짜 미확인" if date == "미확인" else "[모의] 불확실성 예시",
            }
        )
    return out


def _audience_question():
    return {
        "key": "audience",
        "question": "누구를 위한 카드뉴스인가요?",
        "why": "[모의] 독자에 따라 카드 순서와 용어 설명이 크게 달라집니다.",
        "options": [
            {"id": "owner-new", "label": "자동화가 처음인 사장님", "desc": "왜 필요한지부터, 용어는 쉽게"},
            {"id": "owner-ready", "label": "써 보고 싶은 사장님", "desc": "따라 할 순서와 조건 중심"},
            {"id": "staff", "label": "함께 쓰는 직원·강사", "desc": "입력하는 방법과 바뀌는 점 중심"},
        ],
        "recommended": "owner-new",
        "recommendReason": "[모의] 편집 방향이 비어 있어 가장 넓은 독자를 추천합니다.",
        "multiSelect": False,
        "allowFree": True,
    }


def _format_question(audience):
    return {
        "key": "format",
        "question": "어떤 형식으로 만들까요?",
        "why": f"[모의] '{audience}' 독자에게는 두 형식 모두 맞을 수 있어 결과가 갈립니다.",
        "options": [
            {"id": "story", "label": "이야기형", "desc": "상황 → 불편 → 바뀐 점 → 활용 → 한계"},
            {"id": "steps", "label": "단계 안내형", "desc": "준비물 → 1단계 → 2단계 → 결과 확인"},
        ],
        "recommended": "story",
        "recommendReason": "[모의] 처음 보는 독자에게는 변화의 의미부터 보여 주는 편이 쉽습니다.",
        "multiSelect": False,
        "allowFree": True,
    }
