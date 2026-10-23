"""웹 서버: 화면 파일과 /api/* 를 제공한다. 요청·응답 형식은 API_SPEC.md 참고."""

import hashlib
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .store import ACTIVE_STATUSES, NotFound, add_event, find_run, new_id, now_iso

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
            run = self.runner.prepare(doc, kind, "researching" if kind == "research" else "running")
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

        def _send(self, status, data, ctype):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def serve(app, host, port):
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    return httpd
