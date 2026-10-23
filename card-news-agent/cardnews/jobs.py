"""작업 실행기. 엔진 호출을 웹 요청과 분리된 스레드에서 돌린다.

HTTP 요청은 작업 ID를 바로 돌려받고, 화면은 GET /api/projects/{id}로 진행을 본다.
"""

import threading

from .engines.mock import Cancelled
from .store import add_event, find_run, new_id, now_iso

RESULT_TYPES = {"need_input", "result", "error"}


class Runner:
    def __init__(self, store, engine, images=None, renderer=None):
        self.store = store
        self.engine = engine
        self.images = images  # 그림 작업자 (ImageMaker)
        self.renderer = renderer  # 카드 렌더러 (글자 + 그림 → PNG)
        self._cancels = {}

    # --- 문서 수정 (store.update 안에서 호출) ---

    def prepare(self, doc, kind, status, cards=None):
        """새 작업 기록을 doc에 만든다. 실제 실행은 저장 후 launch()로 시작한다.
        cards: 그림 작업에서 만들 카드 번호 목록."""
        run = {
            "id": new_id("run"),
            "kind": kind,
            "status": "running",
            "startedAt": now_iso(),
            "finishedAt": None,
            "error": None,
        }
        if cards is not None:
            run["cards"] = list(cards)
        doc.setdefault("runs", []).append(run)
        doc["currentRunId"] = run["id"]
        doc["status"] = status
        doc["error"] = None
        add_event(doc, f"작업 시작: {kind} ({run['id']})")
        return run

    def launch(self, project_id, run):
        cancel = threading.Event()
        self._cancels[run["id"]] = cancel
        t = threading.Thread(
            target=self._work, args=(project_id, run["id"], run["kind"], cancel), daemon=True
        )
        t.start()

    def cancel(self, run_id):
        ev = self._cancels.get(run_id)
        if ev:
            ev.set()

    # --- 스레드 ---

    def _work(self, project_id, run_id, kind, cancel):
        def emit(message):
            self.store.update(project_id, lambda d: add_event(d, message))

        try:
            doc = self.store.get(project_id)
            if kind in ("images", "render"):
                cards = find_run(doc, run_id).get("cards") or []
                worker = self.images if kind == "images" else self.renderer
                out = worker.run(project_id, run_id, cards, emit, cancel)
            else:
                out = getattr(self.engine, kind)(_context(doc), emit, cancel)
        except Cancelled:
            return
        except Exception as exc:  # 엔진 내부 오류도 화면에 이유를 보여 준다
            out = {"type": "error", "code": "engine_error", "message": f"엔진 호출 중 오류: {exc}"}
        finally:
            self._cancels.pop(run_id, None)
        self.store.update(project_id, lambda d: _apply(d, run_id, kind, out, self.engine.new_session))

    def shutdown(self):
        for ev in list(self._cancels.values()):
            ev.set()
        stop = getattr(self.engine, "stop_all", None)
        if stop:
            stop()


def _context(doc):
    research = doc.get("research") or {}
    chosen = set((doc.get("selection") or {}).get("candidateIds", []))
    return {
        "projectId": doc["id"],
        "sessionId": doc.get("engineSessionId"),
        "sessionStarted": bool(doc.get("engineSessionStarted")),
        "topic": doc["topic"],
        "sourcePath": doc.get("sourcePath"),
        "direction": doc.get("direction"),
        "periodDays": doc.get("periodDays"),
        "selected": [c for c in research.get("candidates", []) if c["id"] in chosen],
        "answers": doc.get("answers", []),
        "editorial": doc.get("editorial"),
        "storyboard": doc.get("storyboard"),
        "storyboardFeedback": doc.get("storyboardFeedback") or [],
    }


def _invalid(out, kind):
    """엔진 결과 형식 검사. 문제가 있으면 이유를 돌려준다."""
    if not isinstance(out, dict) or out.get("type") not in RESULT_TYPES:
        return "엔진 결과의 type이 need_input/result/error 중 하나가 아닙니다."
    t = out["type"]
    if t == "error":
        return None if out.get("message") else "오류 결과에 message가 없습니다."
    if t == "need_input":
        if kind != "editorial":
            return "이 단계에서는 질문을 받을 수 없습니다."
        q = out.get("question") or {}
        if not q.get("key") or not q.get("question") or not q.get("options"):
            return "질문 결과에 key/question/options가 없습니다."
        return None
    if kind == "research":
        r = out.get("research") or {}
        if not isinstance(r.get("candidates"), list):
            return "조사 결과에 candidates 목록이 없습니다."
        return None
    if kind == "storyboard":
        cards = (out.get("storyboard") or {}).get("cards")
        if not isinstance(cards, list) or not 3 <= len(cards) <= 10:
            return "스토리보드 카드가 3~10장이 아닙니다."
        if not all(isinstance(c, dict) and c.get("title") for c in cards):
            return "제목이 없는 카드가 있습니다."
        return None
    if kind == "images":
        return None if isinstance(out.get("images"), dict) else "그림 작업 결과가 없습니다."
    if kind == "render":
        return None if isinstance(out.get("render"), dict) else "카드 만들기 결과가 없습니다."
    if not isinstance(out.get("editorial"), dict):
        return "편집 결과에 editorial이 없습니다."
    return None


def _apply(doc, run_id, kind, out, new_session):
    run = find_run(doc, run_id)
    if run is None or run["status"] != "running" or doc.get("currentRunId") != run_id:
        return  # 취소되었거나 더 새 작업이 있음: 늦게 온 결과는 버린다
    run["finishedAt"] = now_iso()

    problem = _invalid(out, kind)
    if problem:
        out = {"type": "error", "code": "invalid_output", "message": f"잘못된 엔진 출력: {problem}"}

    if out["type"] != "error" and out.get("sessionId"):
        # 이 프로젝트의 엔진 대화. 다음 호출은 이 ID로 이어 간다(--resume).
        doc["engineSessionId"] = out["sessionId"]
        doc["engineSessionStarted"] = True
    elif out["type"] == "error" and not doc.get("engineSessionStarted"):
        # 첫 호출이 실패하면 그 ID가 반쯤 만들어졌을 수 있어 새 ID로 다시 시작한다.
        doc["engineSessionId"] = new_session()

    if out["type"] == "error":
        run["status"] = "failed"
        run["error"] = out["message"]
        doc["status"] = "failed"
        doc["error"] = {"code": out.get("code", "engine_error"), "message": out["message"], "retryKind": kind}
        add_event(doc, f"작업 실패: {out['message']}")
        return

    if out["type"] == "need_input":
        doc["questionSeq"] = doc.get("questionSeq", 0) + 1
        q = dict(out["question"])
        q["id"] = new_id("q")
        q["version"] = doc["questionSeq"]
        q["askedAt"] = now_iso()
        doc["question"] = q
        run["status"] = "waiting"
        doc["status"] = "waiting_for_user"
        add_event(doc, f"질문 대기: {q['question']}")
        return

    run["status"] = "done"
    if kind == "research":
        prev = (doc.get("research") or {}).get("candidatesVersion", 0)
        research = dict(out["research"])
        research["candidatesVersion"] = prev + 1
        doc["research"] = research
        doc["selection"] = {"candidateIds": [], "confirmed": False, "savedAt": None}
        doc["status"] = "candidates_ready"
        add_event(doc, f"후보 {len(research['candidates'])}개를 받았습니다.")
    elif kind == "storyboard":
        prev = doc.get("storyboard") or {}
        sb = dict(out["storyboard"])
        for i, c in enumerate(sb["cards"], start=1):
            c["no"] = i  # 번호는 앱이 1부터 다시 매긴다
            c.pop("image", None)
            c.setdefault("sources", [])
        sb["version"] = int(prev.get("version") or 0) + 1
        sb["approved"] = None
        sb["createdAt"] = now_iso()
        doc["storyboard"] = sb
        doc["status"] = "storyboard_ready"
        add_event(doc, f"스토리보드 {len(sb['cards'])}장 (버전 {sb['version']}). 승인을 기다립니다.")
    elif kind == "images":
        summary = out["images"]
        doc["status"] = "images_ready"
        add_event(doc, f"그림 작업 끝: 완료 {summary['made']}장, 실패 {summary['failed']}장")
    elif kind == "render":
        summary = out["render"]
        doc["status"] = "cards_ready"
        add_event(doc, f"카드 만들기 끝: 완성 {summary['made']}장 (검사 경고 {summary['warned']}장), 실패 {summary['failed']}장")
    else:
        doc["editorial"] = out["editorial"]
        doc["status"] = "editorial_ready"
        add_event(doc, "편집 방향을 정리했습니다.")
