"""웹 서버: 화면 파일과 /api/* 를 제공한다. 요청·응답 형식은 API_SPEC.md 참고."""

import hashlib
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .exports import build_zip, final_ok, ready_for_final, signature, verify_zip
from .render import card_text as card_text_of
from .render import render_stale
from .store import ACTIVE_STATUSES, NotFound, add_event, find_run, new_id, now_iso


def clean_layout(lay):
    """글자 모양 입력 검사. 범위를 벗어나면 400."""
    if not isinstance(lay, dict):
        raise ApiError(400, "bad_request", "layout은 객체여야 합니다.")
    ranges = {"titleSize": (40, 100), "keySize": (26, 64), "bodySize": (26, 52)}
    out = {}
    for k, (lo, hi) in ranges.items():
        v = lay.get(k)
        if not isinstance(v, (int, float)) or not lo <= v <= hi:
            raise ApiError(400, "bad_request", f"{k}는 {lo}~{hi} 사이 숫자여야 합니다.")
        out[k] = int(v)
    if lay.get("color") not in ("dark", "light"):
        raise ApiError(400, "bad_request", "color는 dark 또는 light입니다.")
    out["color"] = lay["color"]
    out["box"] = bool(lay.get("box"))
    return out

STATIC_DIR = Path(__file__).parent / "static"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/static/style.css": ("style.css", "text/css; charset=utf-8"),
}
MAX_BODY = 1_000_000
MAX_SELECT = 3
RESEARCH_ALLOWED = {"created", "candidates_ready", "failed", "interrupted", "cancelled"}
RETRY_ALLOWED = {"failed", "interrupted", "cancelled"}


IMAGE_TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


class FileResponse:
    def __init__(self, path, ctype, download=None):
        self.path = path
        self.ctype = ctype
        self.download = download  # 있으면 내려받기 파일 이름


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class App:
    def __init__(self, store, runner, engine_name, engine_status=None):
        self.store = store
        self.runner = runner
        self.engine_name = engine_name
        # 서버를 켤 때 확인한 엔진 상태 (예: {"ready": False, "note": "로그인 필요"})
        self.engine_status = engine_status or {"ready": True, "note": ""}

    # --- 공통 ---

    def _get(self, project_id):
        try:
            return self.store.get(project_id)
        except NotFound:
            raise ApiError(404, "not_found", "프로젝트를 찾을 수 없습니다.")

    def _update(self, project_id, fn):
        self._get(project_id)
        response, run = self.store.update(project_id, fn)
        if run:
            self.runner.launch(project_id, run)
        return response

    # --- 엔드포인트 ---

    def health(self):
        return {
            "engine": self.engine_name,
            "mock": self.engine_name == "mock",
            "engineReady": self.engine_status["ready"],
            "engineNote": self.engine_status["note"],
            "dataDir": str(self.store.data_dir),
        }

    def list_projects(self):
        return {
            "projects": [
                {
                    "id": d["id"],
                    "topic": d["topic"],
                    "status": d["status"],
                    "engine": d["engine"],
                    "createdAt": d["createdAt"],
                    "updatedAt": d.get("updatedAt"),
                }
                for d in self.store.list()
            ]
        }

    def create_project(self, body):
        topic = str(body.get("topic") or "").strip()
        if not topic:
            raise ApiError(400, "bad_request", "주제를 입력해 주세요.")
        if len(topic) > 200:
            raise ApiError(400, "bad_request", "주제는 200자 이하로 입력해 주세요.")
        period = body.get("periodDays", 7)
        if period not in (7, 30):
            raise ApiError(400, "bad_request", "조사 기간은 7일 또는 30일입니다.")
        source = str(body.get("sourcePath") or "").strip().strip('"') or None
        if source and not (Path(source).is_absolute() and Path(source).is_dir()):
            raise ApiError(400, "bad_request", "자료 위치는 이 PC에 있는 폴더의 전체 경로로 넣어 주세요 (예: C:\\Users\\...\\gangsa-hours).")
        direction = str(body.get("direction") or "").strip() or None
        now = now_iso()
        doc = {
            "id": new_id("prj"),
            "topic": topic,
            "sourcePath": source,
            "sourceExists": Path(source).exists() if source else None,
            "direction": direction,
            "periodDays": period,
            "engine": self.engine_name,
            "engineSessionId": self.runner.engine.new_session(),
            "status": "created",
            "error": None,
            "createdAt": now,
            "updatedAt": now,
            "rev": 0,
            "research": None,
            "selection": {"candidateIds": [], "confirmed": False, "savedAt": None},
            "question": None,
            "questionSeq": 0,
            "answers": [],
            "editorial": None,
            "runs": [],
            "currentRunId": None,
            "events": [{"at": now, "message": f"프로젝트를 만들었습니다 (엔진: {self.engine_name})."}],
            "requests": {},
        }
        self.store.create(doc)
        return {"projectId": doc["id"]}

    def get_project(self, project_id):
        return public_view(self._get(project_id))

    def research(self, project_id, body):
        rid = body.get("requestId")
        period = body.get("periodDays")
        if period is not None and period not in (7, 30):
            raise ApiError(400, "bad_request", "조사 기간은 7일 또는 30일입니다.")

        def fn(doc):
            replay = check_request(doc, rid, "research", {"periodDays": period})
            if replay is not None:
                return replay, None
            if doc["status"] in ACTIVE_STATUSES:
                resp = {"runId": doc["currentRunId"], "status": doc["status"], "alreadyRunning": True}
                remember(doc, rid, "research", {"periodDays": period}, resp)
                return resp, None
            if doc["status"] not in RESEARCH_ALLOWED:
                raise ApiError(409, "invalid_state", "후보를 고른 뒤에는 다시 조사할 수 없습니다.")
            if period is not None:
                doc["periodDays"] = period
            run = self.runner.prepare(doc, "research", "researching")
            resp = {"runId": run["id"], "status": doc["status"]}
            remember(doc, rid, "research", {"periodDays": period}, resp)
            return resp, run

        return self._update(project_id, fn)

    def selection(self, project_id, body):
        rid = body.get("requestId")
        ids = body.get("candidateIds")
        version = body.get("version")
        confirm = bool(body.get("confirm"))
        payload = {"candidateIds": ids, "version": version, "confirm": confirm}
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise ApiError(400, "bad_request", "candidateIds는 문자열 목록이어야 합니다.")

        def fn(doc):
            replay = check_request(doc, rid, "selection", payload)
            if replay is not None:
                return replay, None
            if doc["status"] != "candidates_ready":
                raise ApiError(409, "selection_locked", "지금은 후보 선택을 바꿀 수 없습니다.")
            research = doc.get("research") or {}
            if version != research.get("candidatesVersion"):
                raise ApiError(409, "stale_version", "후보 목록이 바뀌었습니다. 새로고침한 뒤 다시 골라 주세요.")
            known = {c["id"] for c in research.get("candidates", [])}
            if any(i not in known for i in ids):
                raise ApiError(400, "bad_request", "없는 후보가 들어 있습니다.")
            unique = list(dict.fromkeys(ids))
            if len(unique) > MAX_SELECT:
                raise ApiError(400, "bad_request", f"후보는 최대 {MAX_SELECT}개까지 고를 수 있습니다.")
            if confirm and not unique:
                raise ApiError(400, "bad_request", "후보를 하나 이상 골라 주세요.")
            doc["selection"] = {"candidateIds": unique, "confirmed": confirm, "savedAt": now_iso()}
            run = None
            if confirm:
                add_event(doc, f"후보 {len(unique)}개 선택을 확정했습니다: {', '.join(unique)}")
                run = self.runner.prepare(doc, "editorial", "running")
            resp = {"selection": doc["selection"], "status": doc["status"], "runId": run["id"] if run else None}
            remember(doc, rid, "selection", payload, resp)
            return resp, run

        return self._update(project_id, fn)

    def answer(self, project_id, body):
        rid = body.get("requestId")
        qid = body.get("questionId")
        version = body.get("version")
        answer = body.get("answer") or {}
        payload = {"questionId": qid, "version": version, "answer": answer}

        def fn(doc):
            replay = check_request(doc, rid, "answer", payload)
            if replay is not None:
                return replay, None
            q = doc.get("question")
            current = doc["status"] == "waiting_for_user" and q and q["id"] == qid and q["version"] == version
            if not current:
                if any(a["questionId"] == qid for a in doc.get("answers", [])):
                    raise ApiError(409, "already_answered", "이미 답한 질문입니다. 같은 답으로 작업을 다시 시작하지 않습니다.")
                raise ApiError(409, "stale_question", "지난 질문입니다. 화면을 새로 불러와 현재 질문에 답해 주세요.")
            option_id = answer.get("optionId")
            text = str(answer.get("text") or "").strip()
            options = {o["id"]: o for o in q["options"]}
            if option_id:
                if option_id not in options:
                    raise ApiError(400, "bad_request", "없는 선택지입니다.")
                label = options[option_id]["label"]
            elif text and q.get("allowFree"):
                label = text[:200]
            else:
                raise ApiError(400, "bad_request", "선택지를 고르거나 직접 입력해 주세요.")
            doc["answers"].append(
                {
                    "key": q["key"],
                    "questionId": qid,
                    "version": version,
                    "question": q["question"],
                    "optionId": option_id,
                    "text": text or None,
                    "label": label,
                    "answeredAt": now_iso(),
                }
            )
            doc["question"] = None
            add_event(doc, f"답변 저장: {q['question']} → {label}")
            run = self.runner.prepare(doc, "editorial", "running")
            resp = {"accepted": True, "status": doc["status"], "runId": run["id"]}
            remember(doc, rid, "answer", payload, resp)
            return resp, run

        return self._update(project_id, fn)

    def storyboard(self, project_id, body):
        """스토리보드 만들기. feedback이 있으면 변경 요청으로 다시 만든다(승인 전까지만)."""
        rid = body.get("requestId")
        feedback = str(body.get("feedback") or "").strip()
        payload = {"feedback": feedback}

        def fn(doc):
            replay = check_request(doc, rid, "storyboard", payload)
            if replay is not None:
                return replay, None
            if doc["status"] in ACTIVE_STATUSES:
                raise ApiError(409, "invalid_state", "다른 작업이 진행 중입니다.")
            sb = doc.get("storyboard")
            if sb and sb.get("approved"):
                raise ApiError(409, "storyboard_locked", "이미 승인한 스토리보드입니다.")
            if doc["status"] not in ("editorial_ready", "storyboard_ready"):
                raise ApiError(409, "invalid_state", "편집 방향이 정해진 뒤에 스토리보드를 만들 수 있습니다.")
            if feedback:
                if not sb:
                    raise ApiError(400, "bad_request", "변경 요청은 스토리보드가 나온 뒤에 할 수 있습니다.")
                doc.setdefault("storyboardFeedback", []).append(feedback[:1000])
                add_event(doc, f"스토리보드 변경 요청: {feedback[:80]}")
            run = self.runner.prepare(doc, "storyboard", "running")
            resp = {"runId": run["id"], "status": doc["status"]}
            remember(doc, rid, "storyboard", payload, resp)
            return resp, run

        return self._update(project_id, fn)

    def approve(self, project_id, body):
        rid = body.get("requestId")
        stage = body.get("stage")
        version = body.get("version")
        payload = {"stage": stage, "version": version}
        if stage == "final":
            return self._approve_final(project_id, rid, body.get("signature"))
        if stage != "storyboard":
            raise ApiError(400, "bad_request", "stage는 storyboard 또는 final입니다.")

        def fn(doc):
            replay = check_request(doc, rid, "approve", payload)
            if replay is not None:
                return replay, None
            sb = doc.get("storyboard")
            if doc["status"] != "storyboard_ready" or not sb:
                raise ApiError(409, "invalid_state", "승인할 스토리보드가 없습니다.")
            if version != sb.get("version"):
                raise ApiError(409, "stale_version", "스토리보드가 바뀌었습니다. 새로 불러와 다시 확인해 주세요.")
            sb["approved"] = {"version": version, "at": now_iso()}
            for c in sb["cards"]:
                c["image"] = {"status": "pending"}
            add_event(doc, f"스토리보드 버전 {version} 승인. 그림 만들기를 시작합니다.")
            run = self.runner.prepare(doc, "images", "running", cards=[c["no"] for c in sb["cards"]])
            resp = {"runId": run["id"], "status": doc["status"]}
            remember(doc, rid, "approve", payload, resp)
            return resp, run

        return self._update(project_id, fn)

    def card_image(self, project_id, no, body):
        """카드 하나의 그림만 다시 만든다. 다른 카드와 승인한 스토리보드는 그대로 둔다."""
        rid = body.get("requestId")
        no = int(no)

        def fn(doc):
            replay = check_request(doc, rid, "card_image", {"no": no})
            if replay is not None:
                return replay, None
            sb = doc.get("storyboard") or {}
            if not sb.get("approved") or doc["status"] in ACTIVE_STATUSES:
                raise ApiError(409, "invalid_state", "스토리보드 승인 뒤, 다른 작업이 없을 때 다시 만들 수 있습니다.")
            card = next((c for c in sb["cards"] if c["no"] == no), None)
            if card is None:
                raise ApiError(404, "not_found", "없는 카드입니다.")
            card["image"] = dict(card.get("image") or {}, status="pending")
            add_event(doc, f"카드 {no} 그림 다시 만들기")
            run = self.runner.prepare(doc, "images", "running", cards=[no])
            resp = {"runId": run["id"], "status": doc["status"]}
            remember(doc, rid, "card_image", {"no": no}, resp)
            return resp, run

        return self._update(project_id, fn)

    def render(self, project_id, body):
        """카드 만들기: 그림 위에 글자를 올려 PNG로. 그림·글자가 바뀌었거나 아직 없는 카드만."""
        rid = body.get("requestId")

        def fn(doc):
            replay = check_request(doc, rid, "render", {"all": bool(body.get("all"))})
            if replay is not None:
                return replay, None
            sb = doc.get("storyboard") or {}
            if not sb.get("approved") or doc["status"] in ACTIVE_STATUSES:
                raise ApiError(409, "invalid_state", "그림이 만들어진 뒤, 다른 작업이 없을 때 카드를 만들 수 있습니다.")
            todo = [c["no"] for c in sb["cards"] if (c.get("image") or {}).get("status") == "done"
                    and (body.get("all") or render_stale(c, len(sb["cards"])))]
            if not todo:
                resp = {"runId": None, "status": doc["status"], "nothingToDo": True}
                remember(doc, rid, "render", {"all": bool(body.get("all"))}, resp)
                return resp, None
            run = self.runner.prepare(doc, "render", "running", cards=todo)
            resp = {"runId": run["id"], "status": doc["status"], "cards": todo}
            remember(doc, rid, "render", {"all": bool(body.get("all"))}, resp)
            return resp, run

        return self._update(project_id, fn)

    def _approve_final(self, project_id, rid, sig):
        """최종 승인: 지금 화면에 보이는 카드 묶음(signature)에 대해 저장한다. 카드가 바뀌면 자동으로 풀린다."""

        def fn(doc):
            replay = check_request(doc, rid, "approve_final", {"signature": sig})
            if replay is not None:
                return replay, None
            if doc["status"] in ACTIVE_STATUSES:
                raise ApiError(409, "invalid_state", "작업이 진행 중입니다.")
            ok, why = ready_for_final(doc)
            if not ok:
                raise ApiError(409, "not_ready", why)
            if sig != signature(doc):
                raise ApiError(409, "stale_version", "카드가 바뀌었습니다. 새로 불러와 다시 확인해 주세요.")
            doc["finalApproval"] = {"at": now_iso(), "signature": sig}
            add_event(doc, f"최종 승인 (카드 {len(doc['storyboard']['cards'])}장, 서명 {sig})")
            resp = {"finalApproval": doc["finalApproval"]}
            remember(doc, rid, "approve_final", {"signature": sig}, resp)
            return resp, None

        return self._update(project_id, fn)

    def revisions(self, project_id, body):
        """요청문으로 카드 고치기. 고른 카드만, 글만(text) 또는 그림만(image)."""
        rid = body.get("requestId")
        ids = body.get("cardIds")
        instruction = str(body.get("instruction") or "").strip()
        scope = body.get("scope", "text")
        payload = {"cardIds": ids, "instruction": instruction, "scope": scope}
        if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
            raise ApiError(400, "bad_request", "고칠 카드 번호를 하나 이상 골라 주세요.")
        if not instruction or len(instruction) > 500:
            raise ApiError(400, "bad_request", "요청문을 500자 이내로 적어 주세요.")
        if scope not in ("text", "image"):
            raise ApiError(400, "bad_request", "scope는 text 또는 image입니다.")

        def fn(doc):
            replay = check_request(doc, rid, "revisions", payload)
            if replay is not None:
                return replay, None
            sb = doc.get("storyboard") or {}
            if not sb.get("approved") or doc["status"] in ACTIVE_STATUSES:
                raise ApiError(409, "invalid_state", "카드가 만들어진 뒤, 다른 작업이 없을 때 고칠 수 있습니다.")
            known = {c["no"]: c for c in sb["cards"]}
            if any(i not in known or (known[i].get("image") or {}).get("status") != "done" for i in ids):
                raise ApiError(400, "bad_request", "없거나 그림이 없는 카드가 있습니다.")
            add_event(doc, f"카드 고치기 요청({scope}) 카드 {ids}: {instruction[:80]}")
            run = self.runner.prepare(doc, "revise", "running", cards=sorted(set(ids)), instruction=instruction, scope=scope)
            resp = {"runId": run["id"], "status": doc["status"]}
            remember(doc, rid, "revisions", payload, resp)
            return resp, run

        return self._update(project_id, fn)

    def create_export(self, project_id, body):
        rid = body.get("requestId")

        def fn(doc):
            replay = check_request(doc, rid, "export", {})
            if replay is not None:
                return replay, None
            if not final_ok(doc):
                raise ApiError(409, "not_approved", "최종 승인된 카드만 내보낼 수 있습니다. 카드를 확인하고 최종 승인해 주세요.")
            entry = build_zip(doc, self.store.data_dir)
            doc.setdefault("exports", []).append(entry)
            add_event(doc, f"내보내기: {entry['file']} ({entry['bytes'] // 1024} KB)")
            remember(doc, rid, "export", {}, entry)
            return entry, None

        return self._update(project_id, fn)

    def list_exports(self, project_id):
        doc = self._get(project_id)
        cur = signature(doc) if final_ok(doc) else None
        return {"finalOk": final_ok(doc), "exports": [dict(e, current=e.get("signature") == cur) for e in doc.get("exports", [])]}

    def export_file(self, project_id, name):
        doc = self._get(project_id)
        entry = next((e for e in doc.get("exports", []) if e["file"] == name), None)
        path = self.store.data_dir / "projects" / project_id / "exports" / name
        if entry is None or not path.is_file():
            raise ApiError(404, "not_found", "내보낸 파일이 없습니다.")
        if not final_ok(doc) or entry.get("signature") != signature(doc):
            raise ApiError(409, "not_approved", "이 파일은 지금 최종 승인된 카드와 다릅니다. 다시 승인하고 내보내 주세요.")
        return FileResponse(path, "application/zip", download=name)

    def verify_export(self, project_id, name, body):
        doc = self._get(project_id)
        if not any(e["file"] == name for e in doc.get("exports", [])):
            raise ApiError(404, "not_found", "내보낸 파일이 없습니다.")
        rows = verify_zip(doc, self.store.data_dir, name)

        def fn(d):
            for e in d.get("exports", []):
                if e["file"] == name:
                    e["verify"] = {"at": now_iso(), "rows": rows}
            counts = {k: sum(r["result"] == k for r in rows) for k in ("통과", "실패", "확인 못 함")}
            add_event(d, f"내보낸 파일 검증 {name}: 통과 {counts['통과']} · 실패 {counts['실패']} · 확인 못 함 {counts['확인 못 함']}")
            return {"rows": rows, "counts": counts}, None

        return self._update(project_id, fn)

    def card_text(self, project_id, no, body):
        """카드 글자만 고친다. 그림은 다시 만들지 않고 그 카드만 다시 그린다."""
        rid = body.get("requestId")
        no = int(no)
        fields = {k: body.get(k) for k in ("title", "keyLine", "body")}
        layout = body.get("layout")
        payload = {"no": no, **fields, "layout": layout}
        sources = body.get("sources")
        if sources is not None:
            if not isinstance(sources, list) or len(sources) > 10 or not all(isinstance(s, str) and 0 < len(s) <= 300 for s in sources):
                raise ApiError(400, "bad_request", "sources는 300자 이하 글 10개 이내 목록이어야 합니다.")
            payload["sources"] = sources
        limits = {"title": 80, "keyLine": 200, "body": 600}
        for k, v in fields.items():
            if v is not None and (not isinstance(v, str) or len(v) > limits[k]):
                raise ApiError(400, "bad_request", f"{k}는 {limits[k]}자 이하의 글이어야 합니다.")
        if layout is not None:
            layout = clean_layout(layout)

        def fn(doc):
            replay = check_request(doc, rid, "card_text", payload)
            if replay is not None:
                return replay, None
            sb = doc.get("storyboard") or {}
            if not sb.get("approved") or doc["status"] in ACTIVE_STATUSES:
                raise ApiError(409, "invalid_state", "그림이 만들어진 뒤, 다른 작업이 없을 때 고칠 수 있습니다.")
            card = next((c for c in sb["cards"] if c["no"] == no), None)
            if card is None:
                raise ApiError(404, "not_found", "없는 카드입니다.")
            if (card.get("image") or {}).get("status") != "done":
                raise ApiError(409, "invalid_state", "이 카드는 그림이 아직 없습니다.")
            text = dict(card_text_of(card))
            text.update({k: v.strip() for k, v in fields.items() if v is not None})
            card["text"] = text
            if sources is not None:
                card["sources"] = sources
            if "layout" in body:
                if layout is None:
                    card.pop("layout", None)  # 자동 맞춤으로 되돌리기
                else:
                    card["layout"] = layout
            add_event(doc, f"카드 {no} 글자 수정 (그림은 그대로)")
            run = self.runner.prepare(doc, "render", "running", cards=[no])
            resp = {"runId": run["id"], "status": doc["status"]}
            remember(doc, rid, "card_text", payload, resp)
            return resp, run

        return self._update(project_id, fn)

    def remove_card(self, project_id, no, body):
        """카드 한 장을 뺀다(다른 카드와 합칠 때). 번호를 다시 매기고, 그림은 그대로 둔다.
        페이지 번호가 바뀌므로 모든 카드는 다시 그려야 하는 상태가 된다."""
        rid = body.get("requestId")
        no = int(no)

        def fn(doc):
            replay = check_request(doc, rid, "remove_card", {"no": no})
            if replay is not None:
                return replay, None
            sb = doc.get("storyboard") or {}
            if not sb.get("approved") or doc["status"] in ACTIVE_STATUSES:
                raise ApiError(409, "invalid_state", "스토리보드 승인 뒤, 다른 작업이 없을 때 뺄 수 있습니다.")
            if len(sb["cards"]) <= 3:
                raise ApiError(409, "invalid_state", "카드는 3장 이상이어야 합니다.")
            card = next((c for c in sb["cards"] if c["no"] == no), None)
            if card is None:
                raise ApiError(404, "not_found", "없는 카드입니다.")
            sb["cards"] = [c for c in sb["cards"] if c["no"] != no]
            for i, c in enumerate(sb["cards"], start=1):
                c["no"] = i
            sb.setdefault("edits", []).append({"at": now_iso(), "action": "remove", "no": no, "title": card.get("title")})
            sb["version"] = int(sb.get("version") or 0) + 1
            sb["approved"] = dict(sb["approved"], version=sb["version"], note=f"카드 {no} 빼기 (그림은 그대로)")
            add_event(doc, f"카드 {no} '{card.get('title')}'를 뺐습니다. 남은 카드 {len(sb['cards'])}장, 번호를 다시 매김")
            resp = {"cards": len(sb["cards"]), "version": sb["version"], "status": doc["status"]}
            remember(doc, rid, "remove_card", {"no": no}, resp)
            return resp, None

        return self._update(project_id, fn)

    def card_file(self, project_id, name):
        self._get(project_id)
        path = self.store.data_dir / "projects" / project_id / "cards" / name
        if not path.is_file():
            raise ApiError(404, "not_found", "카드 파일이 없습니다.")
        return FileResponse(path, "image/png")

    def image_file(self, project_id, name):
        self._get(project_id)
        path = self.store.data_dir / "projects" / project_id / "images" / name
        if not path.is_file():
            raise ApiError(404, "not_found", "그림 파일이 없습니다.")
        ctype = IMAGE_TYPES.get(path.suffix.lower())
        if not ctype:
            raise ApiError(404, "not_found", "그림 파일이 아닙니다.")
        return FileResponse(path, ctype)

    def retry(self, project_id, body):
        rid = body.get("requestId")

        def fn(doc):
            replay = check_request(doc, rid, "retry", {})
            if replay is not None:
                return replay, None
            if doc["status"] not in RETRY_ALLOWED:
                raise ApiError(409, "invalid_state", "다시 시도할 작업이 없습니다.")
            last = find_run(doc, doc.get("currentRunId"))
            kind = (doc.get("error") or {}).get("retryKind") or (last["kind"] if last else "research")
            cards = None
            if kind == "images":  # 그림을 못 만든 카드만 다시
                cards = [c["no"] for c in doc["storyboard"]["cards"] if (c.get("image") or {}).get("status") != "done"]
            elif kind == "render":  # 아직 못 그린 카드만 다시
                cards = [c["no"] for c in doc["storyboard"]["cards"]
                         if (c.get("image") or {}).get("status") == "done" and render_stale(c, len(doc["storyboard"]["cards"]))]
            run = self.runner.prepare(doc, kind, "researching" if kind == "research" else "running", cards=cards)
            resp = {"runId": run["id"], "status": doc["status"]}
            remember(doc, rid, "retry", {}, resp)
            return resp, run

        return self._update(project_id, fn)

    def cancel_run(self, run_id, body=None):
        for summary in self.store.list():
            if find_run(summary, run_id):
                project_id = summary["id"]
                break
        else:
            raise ApiError(404, "not_found", "작업을 찾을 수 없습니다.")

        def fn(doc):
            run = find_run(doc, run_id)
            if run["status"] != "running":
                return {"runId": run_id, "status": run["status"]}, None
            run["status"] = "cancelled"
            run["finishedAt"] = now_iso()
            for c in (doc.get("storyboard") or {}).get("cards", []):
                img = c.get("image") or {}
                if img.get("status") in ("pending", "generating"):
                    c["image"] = dict(img, status="failed", error="취소했습니다.")
            doc["status"] = "cancelled"
            doc["error"] = {"code": "cancelled", "message": "작업을 취소했습니다. 다시 시도할 수 있습니다.", "retryKind": run["kind"]}
            add_event(doc, f"작업 취소: {run_id}")
            return {"runId": run_id, "status": "cancelled"}, None

        resp = self._update(project_id, fn)
        self.runner.cancel(run_id)
        return resp


def check_request(doc, request_id, kind, payload):
    """같은 requestId·같은 입력이면 저장한 응답을, 다른 입력이면 409를 낸다."""
    if not request_id or not isinstance(request_id, str):
        raise ApiError(400, "bad_request", "requestId가 필요합니다.")
    rec = doc.setdefault("requests", {}).get(request_id)
    if rec is None:
        return None
    if rec["hash"] != _digest(kind, payload):
        raise ApiError(409, "request_conflict", "같은 requestId로 다른 요청이 왔습니다.")
    return dict(rec["response"], replayed=True)


def remember(doc, request_id, kind, payload, response):
    doc.setdefault("requests", {})[request_id] = {"hash": _digest(kind, payload), "response": response}


def _digest(kind, payload):
    raw = json.dumps([kind, payload], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def public_view(doc):
    view = {k: v for k, v in doc.items() if k != "requests"}
    view["activeRun"] = find_run(doc, doc.get("currentRunId"))
    if (doc.get("storyboard") or {}).get("cards"):
        ready, why = ready_for_final(doc)
        view["final"] = {"ready": ready, "reason": why, "signature": signature(doc), "ok": final_ok(doc),
                         "approval": doc.get("finalApproval")}
    return view


ROUTES = [
    ("GET", r"/api/health", "health"),
    ("GET", r"/api/projects", "list_projects"),
    ("POST", r"/api/projects", "create_project"),
    ("GET", r"/api/projects/(?P<pid>prj_\w+)", "get_project"),
    ("POST", r"/api/projects/(?P<pid>prj_\w+)/research", "research"),
    ("POST", r"/api/projects/(?P<pid>prj_\w+)/selection", "selection"),
    ("POST", r"/api/projects/(?P<pid>prj_\w+)/answers", "answer"),
    ("POST", r"/api/projects/(?P<pid>prj_\w+)/retry", "retry"),
    ("POST", r"/api/projects/(?P<pid>prj_\w+)/storyboard", "storyboard"),
    ("POST", r"/api/projects/(?P<pid>prj_\w+)/approve", "approve"),
    ("POST", r"/api/projects/(?P<pid>prj_\w+)/cards/(?P<no>\d{1,2})/image", "card_image"),
    ("POST", r"/api/projects/(?P<pid>prj_\w+)/render", "render"),
    ("POST", r"/api/projects/(?P<pid>prj_\w+)/cards/(?P<no>\d{1,2})/text", "card_text"),
    ("POST", r"/api/projects/(?P<pid>prj_\w+)/cards/(?P<no>\d{1,2})/remove", "remove_card"),
    ("POST", r"/api/projects/(?P<pid>prj_\w+)/revisions", "revisions"),
    ("POST", r"/api/projects/(?P<pid>prj_\w+)/exports", "create_export"),
    ("GET", r"/api/projects/(?P<pid>prj_\w+)/exports", "list_exports"),
    ("GET", r"/api/projects/(?P<pid>prj_\w+)/exports/(?P<name>cardnews-\d{8}-\d{6}\.zip)", "export_file"),
    ("POST", r"/api/projects/(?P<pid>prj_\w+)/exports/(?P<name>cardnews-\d{8}-\d{6}\.zip)/verify", "verify_export"),
    ("GET", r"/api/projects/(?P<pid>prj_\w+)/cards/(?P<name>card-\d{2}-r\d+\.png)", "card_file"),
    ("GET", r"/api/projects/(?P<pid>prj_\w+)/images/(?P<name>card-\d{2}-v\d+\.(?:svg|png|jpg|jpeg|webp))", "image_file"),
    ("POST", r"/api/runs/(?P<rid>run_\w+)/cancel", "cancel_run"),
]


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "cardnews/0.1"

        def log_message(self, fmt, *args):
            if self.path.startswith("/api/") and self.command == "GET":
                return  # 화면의 주기적 조회는 로그에 남기지 않는다
            print(f"[{self.log_date_time_string()}] {self.command} {self.path} {args[1] if len(args) > 1 else ''}")

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in STATIC_FILES:
                name, ctype = STATIC_FILES[path]
                self._send(200, (STATIC_DIR / name).read_bytes(), ctype)
                return
            self._api("GET", path)

        def do_POST(self):
            self._api("POST", self.path.split("?", 1)[0])

        def _api(self, method, path):
            try:
                for m, pattern, name in ROUTES:
                    match = re.fullmatch(pattern, path)
                    if m == method and match:
                        args = list(match.groupdict().values())
                        if method == "POST":
                            args.append(self._body())
                        result = getattr(app, name)(*args)
                        if isinstance(result, FileResponse):
                            self._send(200, result.path.read_bytes(), result.ctype, result.download)
                            return
                        status = 201 if name == "create_project" else 200
                        self._json(status, result)
                        return
                raise ApiError(404, "not_found", "없는 주소입니다.")
            except ApiError as e:
                self._json(e.status, {"error": {"code": e.code, "message": e.message}})
            except Exception as e:  # 서버 내부 오류도 이유를 알려 준다
                self._json(500, {"error": {"code": "internal", "message": f"서버 오류: {e}"}})

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ApiError(413, "too_large", "요청이 너무 큽니다.")
            if length == 0:
                return {}
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise ApiError(400, "bad_request", "JSON 형식이 아닙니다.")
            if not isinstance(body, dict):
                raise ApiError(400, "bad_request", "JSON 객체를 보내 주세요.")
            return body

        def _json(self, status, obj):
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _send(self, status, data, ctype, download=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def serve(app, host, port):
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    return httpd
