"""그림 작업자.

스토리보드를 승인한 뒤 카드마다 그림을 만든다.
1) agy(Antigravity CLI)가 설치·로그인되어 있으면 agy의 내장 generate_image로 만든다.
   agy는 그림을 작업 폴더가 아니라 ~/.gemini/antigravity-cli/brain/<대화 ID>/ 에 저장하므로 거기서 새 파일을 찾아온다.
2) agy를 쓸 수 없거나 실패하면 claude cli가 그린 도형 그림(SVG)으로 대신한다.
어느 쪽이든 파일이 실제 이미지인지 검사한 뒤에만 완료로 표시하고, 어떤 도구로 만들었는지 기록한다.
"""

import json
import os
import re
import shutil
import struct
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from .engines.mock import Cancelled
from .store import add_event, find_run, now_iso

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)
AGY_TIMEOUT = 5 * 60
BRAIN_DIR = Path.home() / ".gemini" / "antigravity-cli" / "brain"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
TOOL_LABELS = {
    "agy": "Antigravity CLI (agy) generate_image",
    "claude-cli-svg": "Claude CLI가 그린 도형 그림(SVG)",
    "mock-svg": "모의 도형 그림(SVG)",
}


class AgyError(Exception):
    def __init__(self, message, fatal=False):
        super().__init__(message)
        self.fatal = fatal  # True면 이번 작업의 남은 카드도 agy를 건너뛴다(로그인·한도 문제)


def find_agy(explicit=None):
    if explicit:
        return explicit
    found = shutil.which("agy")
    if found:
        return found
    default = Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"
    return str(default) if default.exists() else None


class ImageMaker:
    def __init__(self, store, engine, use_agy=True, agy_path=None):
        self.store = store
        self.engine = engine
        self.agy = find_agy(agy_path) if use_agy else None
        self.use_agy = use_agy
        self.fallback_tool = "mock-svg" if engine.name == "mock" else "claude-cli-svg"

    def images_dir(self, project_id):
        d = self.store.data_dir / "projects" / project_id / "images"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # --- 작업 ---

    def run(self, project_id, run_id, card_nos, emit, cancel):
        doc = self.store.get(project_id)
        sb = doc["storyboard"]
        style = sb.get("style") or {}
        agy_state = self.check_agy(emit)
        made = failed = 0
        for no in card_nos:
            if cancel.is_set():
                raise Cancelled()
            card = next(c for c in sb["cards"] if c["no"] == no)
            prev = card.get("image") or {}
            self._set_card(project_id, run_id, no, dict(prev, status="generating", startedAt=now_iso(), error=None))
            emit(f"카드 {no} 그림 만들기 시작")
            rec = self._make_one(doc, card, style, prev, agy_state, emit, cancel)
            had_image = prev.get("file") and prev.get("format")  # 다시 만들기를 누르면 상태는 pending이지만 이전 파일 기록은 남아 있다
            if rec["status"] != "done" and had_image:
                prev = dict(prev, status="done")
                # 다시 만들기가 실패하면 이전 그림을 그대로 두고 실패 이유만 남긴다
                emit(f"카드 {no}: 새 그림을 만들지 못해 이전 그림({prev.get('file')})을 그대로 둡니다.")
                rec = dict(prev, lastAttempt={"at": now_iso(), "error": rec.get("error"), "attempts": rec.get("attempts")})
            self._set_card(project_id, run_id, no, rec)
            if rec["status"] == "done":
                made += 1
                emit(f"카드 {no} 그림 완료: {TOOL_LABELS[rec['tool']]} → {rec['file']} ({rec['format']} {rec.get('width')}×{rec.get('height')})")
            else:
                failed += 1
                emit(f"카드 {no} 그림 실패: {rec['error']}")
        return {"type": "result", "images": {"made": made, "failed": failed, "agy": agy_state}}

    def check_agy(self, emit):
        if not self.use_agy:
            return {"ok": False, "reason": "모의 엔진이라 agy를 쓰지 않습니다."}
        if not self.agy:
            return {"ok": False, "reason": "agy(Antigravity CLI)가 설치되어 있지 않습니다."}
        try:
            out = subprocess.run([self.agy, "models"], capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=90)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "reason": f"agy 상태를 확인하지 못했습니다: {exc}"}
        text = (out.stdout + out.stderr).lower()
        if "sign in" in text or "not logged" in text or "login" in text:
            state = {"ok": False, "reason": "agy에 로그인되어 있지 않습니다. 터미널에서 agy를 실행해 로그인하세요."}
        elif out.returncode != 0:
            state = {"ok": False, "reason": f"agy 상태 확인 실패 (종료 코드 {out.returncode})"}
        else:
            state = {"ok": True, "reason": ""}
        emit("agy 확인: " + ("사용 가능" if state["ok"] else state["reason"] + " → claude cli 도형 그림으로 대신합니다."))
        return state

    def _make_one(self, doc, card, style, prev, agy_state, emit, cancel):
        version = int(prev.get("version") or 0) + 1
        prompt = image_prompt(card, style)
        out_dir = self.images_dir(doc["id"])
        base = f"card-{card['no']:02d}-v{version}"
        attempts = []
        rec = {"version": version, "prompt": prompt, "kind": "생성 이미지", "createdAt": now_iso(),
               "attempts": attempts, "fallbackReason": None, "costUsd": None}

        if agy_state["ok"]:
            try:
                path = self._agy_generate(doc["id"], prompt, out_dir, base, cancel)
                info = verify_image(path)
                return dict(rec, status="done", tool="agy", toolLabel=TOOL_LABELS["agy"], file=path.name, **info)
            except AgyError as exc:
                attempts.append({"tool": "agy", "error": str(exc)})
                emit(f"카드 {card['no']}: agy 실패 — {exc}")
                if exc.fatal:
                    agy_state.update(ok=False, reason=str(exc))
            except ValueError as exc:
                attempts.append({"tool": "agy", "error": f"파일 검사 실패: {exc}"})
        reason = attempts[-1]["error"] if attempts else agy_state["reason"]

        ctx = {"projectId": doc["id"], "sessionId": None}
        cost = 0
        for attempt in (1, 2):  # 모델이 깨진 SVG를 주는 일이 있어 한 번 더 그려 달라고 한다
            res = self.engine.draw_svg(ctx, card, style, emit, cancel)
            cost += res.get("cost") or 0
            if res["type"] != "ok":
                attempts.append({"tool": self.fallback_tool, "error": res.get("message")})
                return dict(rec, status="failed", tool=self.fallback_tool, error=res.get("message") or "그림을 만들지 못했습니다.",
                            fallbackReason=reason, costUsd=cost)
            try:
                svg = sanitize_svg(res["svg"])
                path = out_dir / f"{base}.svg"
                path.write_text(svg, encoding="utf-8")
                info = verify_image(path)
                break
            except ValueError as exc:
                attempts.append({"tool": self.fallback_tool, "error": f"SVG 검사 실패: {exc}"})
                if attempt == 2:
                    return dict(rec, status="failed", tool=self.fallback_tool, error=f"도형 그림 검사 실패: {exc}",
                                fallbackReason=reason, costUsd=cost)
                emit(f"카드 {card['no']}: 도형 그림 코드가 깨져 한 번 더 그립니다.")
        return dict(rec, status="done", tool=self.fallback_tool, toolLabel=TOOL_LABELS[self.fallback_tool],
                    file=path.name, fallbackReason=reason, costUsd=cost, **info)

    def _agy_generate(self, project_id, prompt, out_dir, base, cancel):
        work = self.store.data_dir / "engine-work" / project_id / "agy"
        work.mkdir(parents=True, exist_ok=True)
        request = (f"내장 generate_image 도구만 사용해서 다음 카드뉴스용 일러스트를 한 장 만들어 줘. "
                   f"명령 실행·파일 편집 같은 다른 도구는 쓰지 마. {prompt} "
                   f"현재 작업 폴더의 {base}.png로 저장하고 실제 저장 경로를 알려 줘.")
        started = time.time()
        before = _snapshot([work, BRAIN_DIR])  # 시작 전에 있던 그림은 이번 결과로 치지 않는다
        try:
            proc = subprocess.Popen([self.agy, "-p", request, "--output-format", "json"], cwd=work,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    encoding="utf-8", errors="replace")
        except OSError as exc:
            raise AgyError(f"agy를 실행하지 못했습니다: {exc}", fatal=True)
        while proc.poll() is None:
            if cancel.is_set():
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
                raise Cancelled()
            if time.time() - started > AGY_TIMEOUT:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
                raise AgyError(f"agy가 {AGY_TIMEOUT // 60}분 안에 끝나지 않았습니다.")
            time.sleep(0.5)
        out, err = proc.communicate()
        text = out + err
        low = text.lower()
        if "resource_exhausted" in low or "429" in low or "quota" in low:
            raise AgyError("agy 이미지 할당량 초과 (429 RESOURCE_EXHAUSTED)", fatal=True)
        if "sign in" in low or "not logged" in low:
            raise AgyError("agy 로그인이 필요합니다.", fatal=True)
        if ("permission" in low and "denied" in low) or "soft-den" in low:
            # 실제로 본 경우: agy가 generate_image 대신 RunCommand를 시도해 print 모드에서 거부됨.
            # 이번 카드만 대신하고 다음 카드는 다시 agy를 쓴다.
            raise AgyError("agy가 그림 도구 대신 다른 도구(명령 실행 등)를 쓰려다 거부되었습니다.")
        found = _find_new_image(work, _conversation_id(out), before)
        if not found:
            raise AgyError("agy 응답은 끝났지만 새 그림 파일을 찾지 못했습니다 (작업 폴더와 brain 폴더 확인).")
        dest = out_dir / f"{base}{found.suffix.lower()}"
        shutil.copyfile(found, dest)
        return dest

    def _set_card(self, project_id, run_id, no, image):
        def fn(doc):
            run = find_run(doc, run_id)
            if run is None or run["status"] != "running" or doc.get("currentRunId") != run_id:
                raise Cancelled()  # 취소되었거나 더 새 작업이 있음
            for c in doc["storyboard"]["cards"]:
                if c["no"] == no:
                    c["image"] = image

        self.store.update(project_id, fn)


def image_prompt(card, style):
    palette = ", ".join(style.get("palette") or [])
    return (f"장면: {card.get('imagePlan') or card.get('title')}. 역할: {card.get('imageRole') or ''}. "
            f"그림체: {style.get('illustration') or '단순한 평면 일러스트'}, 분위기: {style.get('mood') or ''}, 색: {palette}. "
            f"세로 4:5 구도, {style.get('layout') or '위쪽 40%는 제목을 올릴 빈 여백'}. "
            "이미지 안에 글자·숫자·로고 없음. 실제 제품 화면이나 실제 사진처럼 보이지 않게.")


def _conversation_id(stdout):
    try:
        data = json.loads(stdout)
    except ValueError:
        lines = [l for l in stdout.splitlines() if l.strip().startswith("{")]
        try:
            data = json.loads(lines[-1]) if lines else {}
        except ValueError:
            data = {}

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if "conversation" in k.lower() and isinstance(v, str) and v:
                    return v
                r = walk(v)
                if r:
                    return r
        elif isinstance(o, list):
            for v in o:
                r = walk(v)
                if r:
                    return r
        return None

    return walk(data)


def _image_files(dirs):
    for d in dirs:
        if d.is_dir():
            for f in d.rglob("*"):
                if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                    yield f


def _snapshot(dirs):
    return {str(f): f.stat().st_mtime for f in _image_files(dirs)}


def _find_new_image(work, conversation_id, before):
    """agy 실행 뒤 새로 생기거나 바뀐 그림 하나. 대화 ID를 알면 그 대화 폴더와 작업 폴더만 본다."""
    if conversation_id:
        dirs = [work, BRAIN_DIR / conversation_id]
    else:
        dirs = [work, BRAIN_DIR]
    files = [f for f in _image_files(dirs)
             if str(f) not in before or f.stat().st_mtime > before[str(f)]]
    return max(files, key=lambda f: f.stat().st_mtime) if files else None


def sanitize_svg(text):
    """모델이 준 SVG에서 스크립트·글자·외부 참조를 빼고 1080×1350으로 맞춘다."""
    m = re.search(r"```(?:svg|xml)?\s*(<svg.*?</svg>)\s*```", text, re.S) or re.search(r"(<svg.*?</svg>)", text, re.S)
    if not m:
        raise ValueError("SVG 코드를 찾지 못했습니다.")
    try:
        root = ET.fromstring(m.group(1))
    except ET.ParseError as exc:
        raise ValueError(f"SVG 형식 오류: {exc}")
    if not root.tag.endswith("svg"):
        raise ValueError("최상위 요소가 svg가 아닙니다.")
    banned = {"script", "foreignObject", "text", "tspan", "image", "a"}
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag.split("}")[-1] in banned:
                parent.remove(child)
    for el in root.iter():
        for attr in list(el.attrib):
            name = attr.split("}")[-1]
            if name.startswith("on") or (name == "href" and not el.attrib[attr].startswith("#")):
                del el.attrib[attr]
    root.set("viewBox", root.get("viewBox") or "0 0 1080 1350")
    root.set("width", "1080")
    root.set("height", "1350")
    if len(list(root.iter())) < 3:
        raise ValueError("도형이 거의 없습니다.")
    return ET.tostring(root, encoding="unicode")


def verify_image(path):
    """파일이 실제 이미지인지 형식과 크기를 확인한다. 아니면 ValueError."""
    path = Path(path)
    data = path.read_bytes()
    if not data:
        raise ValueError("빈 파일입니다.")
    info = {"bytes": len(data)}
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        return dict(info, format="PNG", width=w, height=h)
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return dict(info, format="JPEG", width=w, height=h)
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg
        raise ValueError("JPEG 크기를 읽지 못했습니다.")
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return dict(info, format="WEBP", width=None, height=None)
    try:
        root = ET.fromstring(data.decode("utf-8"))
    except (ET.ParseError, UnicodeDecodeError):
        raise ValueError("PNG·JPEG·WEBP·SVG 중 어느 형식도 아닙니다.")
    if not root.tag.endswith("svg"):
        raise ValueError("SVG가 아닙니다.")
    return dict(info, format="SVG", width=int(float(root.get("width", 0))), height=int(float(root.get("height", 0))))


def mark_interrupted_cards(doc):
    sb = doc.get("storyboard") or {}
    for c in sb.get("cards", []):
        img = c.get("image") or {}
        if img.get("status") in ("pending", "generating"):
            c["image"] = dict(img, status="failed", error="서버가 다시 시작되어 그림 만들기가 중단되었습니다.")
            add_event(doc, f"카드 {c['no']} 그림: 중단됨으로 표시")
