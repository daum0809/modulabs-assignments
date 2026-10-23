"""Claude CLI 엔진.

서버에서 `claude -p`를 실행하고 stream-json 출력을 읽는다.
- 프롬프트는 명령줄이 아니라 stdin으로 넘긴다(주제에 특수문자가 있어도 명령으로 해석되지 않게).
- Windows의 npm `claude.cmd` 대신 그 안의 `claude.exe`를 직접 부른다(.cmd는 cmd.exe가 인자를 다시 해석함).
- 프로젝트마다 세션 ID를 따로 쓴다. 첫 호출은 --session-id, 그다음은 --resume (--continue는 쓰지 않음).
- 결과 문장 안의 JSON만 믿고, 형식이 틀리면 완료로 처리하지 않는다.
"""

import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from .mock import Cancelled

ALLOWED_TOOLS = ["WebSearch", "WebFetch", "Read", "Glob", "Grep"]
DISALLOWED_TOOLS = ["Bash", "Edit", "Write", "NotebookEdit", "Task"]
CALL_TIMEOUT = 15 * 60
# 데스크톱 앱 안에서 켠 셸이 물려준 호스트 세션 변수. 앱이 부르는 claude에는 넘기지 않는다.
HOST_ENV_PREFIXES = ("CLAUDECODE", "CLAUDE_CODE_", "CLAUDE_AGENT_SDK_", "CLAUDE_PID")


def find_claude(explicit=None):
    """실행할 claude 실행 파일 경로. npm 설치면 claude.cmd 옆의 claude.exe를 찾는다."""
    if explicit:
        return explicit
    found = shutil.which("claude")
    if not found:
        raise FileNotFoundError("claude 명령을 찾을 수 없습니다. Claude Code CLI를 설치했는지 확인하세요.")
    path = Path(found)
    if os.name == "nt" and path.suffix.lower() != ".exe":
        exe = path.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if exe.exists():
            return str(exe)
        raise FileNotFoundError(f"{path} 은(는) .cmd 래퍼라 직접 실행하지 않습니다. --claude-path로 claude.exe를 지정하세요.")
    return str(path)


def clean_env():
    env = dict(os.environ)
    from_host = "CLAUDE_CODE_DESKTOP_APP_VERSION" in env or "CLAUDECODE" in env
    for key in list(env):
        if key.startswith(HOST_ENV_PREFIXES):
            env.pop(key)
    if from_host:
        env.pop("ANTHROPIC_BASE_URL", None)
    return env


class ClaudeCliEngine:
    name = "claude-cli"

    def __init__(self, work_dir, claude_path=None, model="sonnet", effort="medium", fail=None, **_):
        self.exe = find_claude(claude_path)
        self.work_dir = Path(work_dir)
        self.model = model
        self.effort = effort
        self._procs = {}
        self._lock = threading.Lock()

    def new_session(self):
        return str(uuid.uuid4())

    # --- 두 작업 ---

    def research(self, ctx, emit, cancel):
        now = datetime.now().astimezone()
        days = ctx.get("periodDays") or 7
        start = (now - timedelta(days=days)).date().isoformat()
        prompt = _research_prompt(ctx, now, start)
        emit(f"Claude CLI 호출: 넓은 조사 (모델 {self.model}, effort {self.effort})")
        call = self._call(ctx, prompt, emit, cancel)
        if call["type"] == "error":
            return call
        data = call["data"]
        if data.get("status") == "error":
            return {"type": "error", "code": data.get("code") or "search_failed",
                    "message": data.get("message") or "엔진이 조사 실패를 알렸습니다.", "sessionId": call["sessionId"]}
        cands = data.get("candidates")
        if not isinstance(cands, list):
            return _bad("candidates 목록이 없습니다.", call)
        trace = call["trace"]
        if not ctx.get("sourcePath") and not trace["searches"]:
            return {"type": "error", "code": "search_failed",
                    "message": "웹 검색이 한 번도 실행되지 않았습니다. 검색 결과 없이 후보를 만들지 않습니다.",
                    "sessionId": call["sessionId"]}
        read = set(trace["fetched"]) | set(trace["files"])
        for i, c in enumerate(cands, start=1):
            c.setdefault("id", f"c{i}")
            c["id"] = str(c["id"])
            c.setdefault("date", "미확인")
            src = str(c.get("source") or "")
            c["sourceRead"] = any(src and (src in r or r in src) for r in read)
        return {
            "type": "result",
            "sessionId": call["sessionId"],
            "research": {
                "researchedAt": now.isoformat(timespec="seconds"),
                "timezone": now.tzname() or "",
                "periodStart": start,
                "periodEnd": now.date().isoformat(),
                "periodDays": days,
                "sourcePath": ctx.get("sourcePath"),
                "note": data.get("note") or "",
                "mock": False,
                "candidates": cands,
                "trace": trace,
                "costUsd": call["cost"],
            },
        }

    def editorial(self, ctx, emit, cancel):
        prompt = _editorial_prompt(ctx)
        emit("Claude CLI 호출: 심층 검증과 편집 판단" + (" (답변 반영)" if ctx.get("answers") else ""))
        call = self._call(ctx, prompt, emit, cancel)
        if call["type"] == "error":
            return call
        data = call["data"]
        status = data.get("status")
        answered = {a["key"] for a in ctx.get("answers", [])}
        if status == "need_input":
            q = data.get("question") or {}
            if q.get("key") in answered:
                return _bad(f"이미 답한 질문({q.get('key')})을 다시 물었습니다.", call)
            if not q.get("question") or not isinstance(q.get("options"), list) or not q["options"]:
                return _bad("질문에 question/options가 없습니다.", call)
            for i, o in enumerate(q["options"], start=1):
                o["id"] = str(o.get("id") or f"o{i}")
            q.setdefault("allowFree", True)
            q.setdefault("multiSelect", False)
            return {"type": "need_input", "question": q, "sessionId": call["sessionId"]}
        if status == "result" and isinstance(data.get("editorial"), dict):
            ed = data["editorial"]
            ed["mock"] = False
            ed["trace"] = call["trace"]
            ed["costUsd"] = call["cost"]
            return {"type": "result", "editorial": ed, "sessionId": call["sessionId"]}
        if status == "error":
            return {"type": "error", "code": data.get("code") or "engine_error",
                    "message": data.get("message") or "엔진이 오류를 알렸습니다.", "sessionId": call["sessionId"]}
        return _bad("status가 need_input/result/error가 아닙니다.", call)

    def stop_all(self):
        with self._lock:
            procs = list(self._procs.values())
        for p in procs:
            _kill_tree(p)

    # --- CLI 호출 ---

    def _call(self, ctx, prompt, emit, cancel):
        cwd = self.work_dir / ctx["projectId"]
        cwd.mkdir(parents=True, exist_ok=True)
        args = [self.exe, "-p", "--output-format", "stream-json", "--verbose",
                "--model", self.model, "--effort", self.effort, "--strict-mcp-config",
                "--allowedTools", *ALLOWED_TOOLS, "--disallowedTools", *DISALLOWED_TOOLS]
        if ctx.get("sourcePath"):
            args += ["--add-dir", ctx["sourcePath"]]
        sid = ctx.get("sessionId")
        args += ["--resume", sid] if ctx.get("sessionStarted") else ["--session-id", sid]

        try:
            proc = subprocess.Popen(
                args, cwd=cwd, env=clean_env(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        except OSError as exc:
            return {"type": "error", "code": "engine_unavailable", "message": f"claude를 실행하지 못했습니다: {exc}"}
        key = id(proc)
        with self._lock:
            self._procs[key] = proc
        stderr_tail = []
        threading.Thread(target=_drain, args=(proc.stderr, stderr_tail), daemon=True).start()

        def feed():
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
            except OSError:
                pass

        threading.Thread(target=feed, daemon=True).start()

        lines = []
        reader = threading.Thread(target=_read_lines, args=(proc.stdout, lines), daemon=True)
        reader.start()
        trace = {"searches": [], "fetched": [], "files": []}
        final = None
        session = sid
        seen = 0
        deadline = time.monotonic() + CALL_TIMEOUT
        try:
            while True:
                if cancel.is_set():
                    _kill_tree(proc)
                    raise Cancelled()
                if time.monotonic() > deadline:
                    _kill_tree(proc)
                    return {"type": "error", "code": "timeout", "message": f"엔진이 {CALL_TIMEOUT // 60}분 안에 끝나지 않아 멈췄습니다."}
                while seen < len(lines):
                    ev = lines[seen]
                    seen += 1
                    session = ev.get("session_id") or session
                    if ev.get("type") == "assistant":
                        for part in (ev.get("message") or {}).get("content") or []:
                            if part.get("type") == "tool_use":
                                _note_tool(part, trace, emit)
                    elif ev.get("type") == "result":
                        final = ev
                if not reader.is_alive() and seen >= len(lines):
                    break
                time.sleep(0.2)
            proc.wait(timeout=10)
        finally:
            with self._lock:
                self._procs.pop(key, None)

        if final is None:
            tail = " ".join(stderr_tail)[-400:]
            return {"type": "error", "code": "engine_error",
                    "message": f"claude가 결과 없이 끝났습니다 (종료 코드 {proc.returncode}). {tail}".strip()}
        text = str(final.get("result") or "")
        if final.get("is_error") or final.get("subtype") != "success":
            return _classify_error(text or final.get("subtype", ""), session)
        data = _extract_json(text)
        if not isinstance(data, dict):
            return {"type": "error", "code": "invalid_output", "sessionId": session,
                    "message": "엔진 답변에서 약속한 JSON을 찾지 못했습니다. 완료로 처리하지 않습니다."}
        emit(f"Claude CLI 응답 수신 (세션 {session[:8]}…, 비용 약 ${final.get('total_cost_usd') or 0:.3f})")
        return {"type": "ok", "data": data, "sessionId": session, "trace": trace,
                "cost": final.get("total_cost_usd")}


def _bad(problem, call):
    return {"type": "error", "code": "invalid_output", "sessionId": call.get("sessionId"),
            "message": f"잘못된 엔진 출력: {problem}"}


def _classify_error(text, session):
    low = text.lower()
    if any(w in low for w in ("authenticate", "oauth", "log in", "login", "/login", "api key")):
        return {"type": "error", "code": "auth_required", "sessionId": session,
                "message": f"Claude CLI 로그인이 필요합니다. 터미널에서 `claude auth login`으로 로그인한 뒤 다시 시도하세요. ({text[:160]})"}
    if any(w in low for w in ("rate limit", "usage limit", "quota", "429", "overloaded")):
        return {"type": "error", "code": "usage_limit", "sessionId": session,
                "message": f"사용 한도에 걸렸습니다. 잠시 뒤 다시 시도하세요. ({text[:160]})"}
    return {"type": "error", "code": "engine_error", "sessionId": session, "message": f"엔진 오류: {text[:300]}"}


def _note_tool(part, trace, emit):
    name = part.get("name")
    inp = part.get("input") or {}
    if name == "WebSearch":
        q = str(inp.get("query") or "")
        trace["searches"].append(q)
        emit(f"검색: {q}")
    elif name == "WebFetch":
        u = str(inp.get("url") or "")
        trace["fetched"].append(u)
        emit(f"원문 읽기: {u}")
    elif name == "Read":
        f = str(inp.get("file_path") or "")
        trace["files"].append(f)
        emit(f"파일 읽기: {f}")
    elif name in ("Glob", "Grep"):
        emit(f"파일 찾기({name}): {inp.get('pattern', '')}")


def _extract_json(text):
    fences = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    for chunk in reversed(fences):
        try:
            return json.loads(chunk)
        except ValueError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except ValueError:
            return None
    return None


def _read_lines(stream, out):
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            pass


def _drain(stream, tail):
    for line in stream:
        tail.append(line.strip())
        del tail[:-20]


def _kill_tree(proc):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()


# --- 프롬프트 ---

OUTPUT_RULE = """
답변의 마지막에 아래 형식의 JSON 하나만 ```json 코드 블록으로 붙인다. JSON 밖의 설명은 짧게 해도 되지만, 앱은 JSON만 읽는다.
모르는 내용을 그럴듯하게 채우지 않는다. 확인하지 못한 날짜는 "미확인"으로 쓴다.
""".strip()


def _research_prompt(ctx, now, start):
    topic = ctx["topic"]
    source = ctx.get("sourcePath")
    direction = ctx.get("direction") or "(없음)"
    if source:
        how = f"""
조사 대상은 사용자의 자료 폴더다: {source}
- Glob/Grep/Read로 이 폴더의 README, 문서, 코드를 읽고 카드뉴스에 쓸 이야깃거리 후보를 만든다.
- 후보의 source에는 근거 파일 경로를 쓰고, date에는 문서에 적힌 날짜(작성일·배포 확인일 등)를 쓴다. 없으면 "미확인".
- 자료에 적힌 효과(절약한 시간 등)는 운영자 경험이다. 확인된 사실처럼 쓰지 않는다.
- 법·세금·제도처럼 자료 밖의 사실은 이 단계에서 확정하지 않는다(다음 단계에서 공식 자료와 대조).""".strip()
    else:
        how = f"""
WebSearch로 실제 검색하고, 중요한 후보는 WebFetch로 원문을 연다.
- 조사 기준 시각: {now.isoformat(timespec='minutes')} / 조사 기간: {start} ~ {now.date().isoformat()}
- 기간 밖의 발표를 새 소식으로 분류하지 않는다. 최근에 쓴 소개 글이라도 원래 발표가 오래됐으면 제외한다.
- 같은 발표를 다룬 기사는 하나로 묶는다. 모델·제품·연구·개발 도구 등으로 다양하게.
- 검색 도구를 쓸 수 없거나 검색이 실패하면 후보를 지어내지 말고 status "error", code "search_failed"로 답한다.""".strip()
    return f"""너는 카드뉴스 제작 앱의 조사 담당이다. 지금은 '넓은 조사' 단계다.

주제: {topic}
편집 방향: {direction}

{how}

가능하면 서로 다른 후보 7~12개. 부족하면 실제로 찾은 만큼만 낸다(채우지 않는다).
후보마다: id(c1, c2…), title, summary(한두 문장), kind(모델/제품/연구/개발 도구/정책/기능/설계/한계 등),
date(게시일 또는 문서 날짜, 모르면 "미확인"), eventDate(실제 발표·변경일, 모르면 "미확인"),
source(원문 URL 또는 파일 경로), value(고를 가치), uncertainty(불확실한 점).

{OUTPUT_RULE}
```json
{{"status": "result", "note": "조사 범위나 한계를 한 줄로", "candidates": [{{"id": "c1", "title": "", "summary": "", "kind": "", "date": "", "eventDate": "", "source": "", "value": "", "uncertainty": ""}}]}}
```
실패하면: ```json
{{"status": "error", "code": "search_failed", "message": "이유"}}
```"""


def _editorial_prompt(ctx):
    selected = json.dumps(ctx.get("selected", []), ensure_ascii=False, indent=1)
    answers = ctx.get("answers", [])
    answered = "\n".join(f"- [{a['key']}] {a['question']} → {a['label']}" for a in answers) or "(아직 없음)"
    asked = ", ".join(sorted({a["key"] for a in answers})) or "(없음)"
    return f"""너는 카드뉴스 제작 앱의 편집 담당이다. 지금은 '심층 검증과 편집 판단' 단계다.
(이 대화가 이어지는 경우에도 아래 정보가 최신이다.)

주제: {ctx['topic']}
자료 위치: {ctx.get('sourcePath') or '(웹 조사)'}
편집 방향(사용자 입력): {ctx.get('direction') or '(없음)'}
사용자가 고른 후보:
{selected}
지금까지 받은 답변:
{answered}

할 일:
1. 고른 후보를 원문(공식 발표·제품 문서·변경 기록, 또는 자료 폴더의 파일)으로 확인한다. 법·세금·제도 내용은 WebSearch/WebFetch로 공식 자료(정부 기관 등)와 대조한다.
   확인한 사실 / 발표 주체(또는 운영자)의 주장 / 아직 확인하지 못한 것을 나누고, 각각 근거 링크나 파일 경로를 붙인다. 자료끼리 날짜·조건이 다르면 conflicts에 적는다.
2. 독자와 독자에게 유용한 이유를 판단한다. 편집 방향에 독자가 있으면 그것을 따르고 다시 묻지 않는다.
3. 카드 형식은 두 가설을 비교해 하나를 추천한다:
   - 이야기형: 자동화가 왜 필요한지 아직 와닿지 않는 독자. 상황 → 불편 → 바뀐 점 → 활용 → 한계.
   - 단계 안내형: 이미 써 보고 싶은 독자. 준비물 → 1단계 → 2단계 → 결과 확인.
4. 표지 문장 2~3개. 확인한 사실의 범위 안에서만 쓰고, 확인하지 않은 효과·수치는 넣지 않는다. 각 문장의 근거를 basis에 쓴다.
   '최신·새로' 같은 시점 표현은 날짜 근거가 있을 때만 쓴다.

질문 규칙: 독자나 편집 방향에 따라 결과가 **크게** 달라질 때만 짧은 객관식 질문 하나를 한다(need_input).
이미 답한 key({asked})는 다시 묻지 않는다. key는 audience / format / angle 중 하나. 각 선택지의 차이를 desc에 한 줄로 쓴다.
판단할 수 있으면 묻지 말고 추천 이유와 함께 result를 낸다.

{OUTPUT_RULE}
질문할 때: ```json
{{"status": "need_input", "question": {{"key": "audience", "question": "", "why": "왜 결과가 갈리는지 한 줄", "options": [{{"id": "a", "label": "", "desc": ""}}], "recommended": "a", "recommendReason": "", "allowFree": true}}}}
```
판단을 마쳤을 때: ```json
{{"status": "result", "editorial": {{"audience": "독자(짧게)", "audienceReason": "", "purpose": "읽고 나서 할 행동", "formatCompare": [{{"format": "이야기형", "pros": "", "cons": ""}}, {{"format": "단계 안내형", "pros": "", "cons": ""}}], "format": "추천 형식", "formatReason": "", "hooks": [{{"text": "", "basis": ""}}], "verification": {{"facts": [{{"text": "", "source": ""}}], "claims": [{{"text": "", "source": ""}}], "unknown": [{{"text": "", "source": ""}}]}}, "conflicts": []}}}}
```"""
