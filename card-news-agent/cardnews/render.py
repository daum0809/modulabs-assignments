"""카드 렌더러 (STEP 8).

그림 위에 제목·핵심 문장·본문을 '따로' 올려 1080×1350 PNG를 만든다. 글자를 고쳐도 그림은 다시 만들지 않는다.
렌더러는 이 PC에 설치된 Chrome(없으면 Edge)의 화면 없는 모드(--headless)를 쓴다.
1) 카드 HTML을 만든다(그림은 data URI로 넣어 다른 파일에 기대지 않음).
2) --dump-dom 으로 페이지 안의 검사 결과(글자 넘침·명암 대비·휴대폰 글자 크기)를 읽는다.
3) --screenshot 으로 PNG를 찍고, 파일 형식·크기를 검사한다.
"""

import base64
import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .engines.mock import Cancelled
from .images import verify_image
from .store import find_run, now_iso

W, H = 1080, 1350
TEXT_LIMIT = 620  # 글자는 위쪽 여백(그림이 비워 둔 곳) 안에 들어가야 한다
PHONE_WIDTH = 375  # 휴대폰 미리보기 너비. 카드가 이 너비로 줄어들 때 본문이 12px 이상이어야 읽힌다
MIN_CONTRAST = 4.5
MIME = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
TOOL_NOTE = {"agy": "AI 생성 그림 (Antigravity)", "claude-cli-svg": "AI 도형 그림 (Claude CLI)", "mock-svg": "모의 그림"}
DEFAULT_LAYOUT = {"titleSize": 68, "keySize": 40, "bodySize": 36, "color": "dark", "box": False}
# 사용자가 글자 모양을 정하지 않았을 때 차례로 시도한다. 검사를 통과하는 첫 번째를 쓴다.
AUTO_LAYOUTS = [
    DEFAULT_LAYOUT,
    dict(DEFAULT_LAYOUT, titleSize=58, keySize=36),
    dict(DEFAULT_LAYOUT, titleSize=58, keySize=36, box=True),
]
BOX_LIMIT = H - 120  # 상자를 깔면 그림 위로 내려가도 되지만 아래 표시줄은 가리지 않는다


def find_chrome(explicit=None):
    if explicit:
        return explicit
    for name in ("chrome", "msedge", "google-chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if Path(p).exists():
            return p
    return None


def card_text(card):
    """카드에 올릴 글자. 사용자가 고친 글자가 있으면 그것을, 없으면 스토리보드 원고를 쓴다."""
    t = card.get("text") or {}
    return {"title": t.get("title", card.get("title", "")), "keyLine": t.get("keyLine", card.get("keyLine", "")),
            "body": t.get("body", card.get("body", ""))}


def card_layout(card):
    return dict(DEFAULT_LAYOUT, **(card.get("layout") or {}))


def _dark_color(palette):
    def lum(h):
        h = h.lstrip("#")
        if len(h) != 6:
            return 1
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    valid = [c for c in palette or [] if re.fullmatch(r"#[0-9a-fA-F]{6}", c)]
    darkest = min(valid, key=lum) if valid else "#1F2328"
    return darkest if lum(darkest) < 0.25 else "#1F2328"


def card_html(card, total, style, image_src, tool, checks=True, layout=None):
    t = card_text(card)
    lay = layout or card_layout(card)
    limit = BOX_LIMIT if lay["box"] else TEXT_LIMIT
    color = "#FFFFFF" if lay["color"] == "light" else _dark_color(style.get("palette"))
    box_bg = "rgba(20,24,32,.72)" if lay["color"] == "light" else "rgba(255,255,255,.86)"
    body = "".join(f"<p>{html.escape(line)}</p>" for line in t["body"].split("\n") if line.strip())
    script = ""
    if checks:
        script = f"""<script>
window.addEventListener('load', () => {{
  const r = {{limit: {limit}}};
  const box = document.querySelector('.text').getBoundingClientRect();
  r.textBottom = Math.round(box.bottom);
  r.overflow = box.bottom > {limit};
  r.wideWord = [...document.querySelectorAll('.text h1, .text .key, .text p')].some(e => e.scrollWidth > e.clientWidth + 1);
  r.phoneBodyPx = Math.round({lay['bodySize']} * {PHONE_WIDTH} / {W} * 10) / 10;
  r.smallOnPhone = r.phoneBodyPx < 12;
  const hex = '{color}'.replace('#', '');
  const lin = v => {{ v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }};
  const L = (R, G, B) => 0.2126 * lin(R) + 0.7152 * lin(G) + 0.0722 * lin(B);
  const tl = L(parseInt(hex.substr(0, 2), 16), parseInt(hex.substr(2, 2), 16), parseInt(hex.substr(4, 2), 16));
  const ratio = (a, b) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  try {{
    const img = document.getElementById('bg');
    const c = document.createElement('canvas'); c.width = {W}; c.height = {H};
    const g = c.getContext('2d');
    const s = Math.max({W} / img.naturalWidth, {H} / img.naturalHeight);
    const w = img.naturalWidth * s, h = img.naturalHeight * s;
    g.drawImage(img, ({W} - w) / 2, ({H} - h) / 2, w, h);
    {"const bx = document.querySelector('.text'); const cs = getComputedStyle(bx).backgroundColor; " if lay["box"] else ""}
    const d = g.getImageData(Math.max(0, box.left), Math.max(0, box.top), Math.max(1, Math.min(box.width, {W} - box.left)), Math.max(1, Math.min(box.height, {H} - box.top))).data;
    const vals = [];
    for (let i = 0; i < d.length; i += 4 * 13) vals.push(ratio(tl, L(d[i], d[i + 1], d[i + 2])));
    vals.sort((a, b) => a - b);
    // 글자 영역에 그림(어두운 도형 등)이 조금이라도 겹치면 찾도록 낮은 대비 점의 비율도 본다
    r.contrast = {"null" if lay["box"] else "Math.round(vals[Math.floor(vals.length * 0.1)] * 10) / 10"};
    r.overlapPct = {"0" if lay["box"] else "Math.round(vals.filter(v => v < 3).length / vals.length * 1000) / 10"};
  }} catch (e) {{ r.contrast = null; r.overlapPct = 0; r.contrastError = String(e); }}
  r.lowContrast = (r.contrast !== null && r.contrast < {MIN_CONTRAST}) || r.overlapPct > 3;
  document.body.setAttribute('data-checks', JSON.stringify(r));
}});
</script>"""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
html, body {{ margin: 0; width: {W}px; height: {H}px; overflow: hidden; background: #f7f4ee; }}
.card {{ position: relative; width: {W}px; height: {H}px; font-family: "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; color: {color}; }}
#bg {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }}
.text {{ position: absolute; left: 84px; right: 84px; top: 96px; {"background: " + box_bg + "; padding: 36px 40px; border-radius: 28px;" if lay["box"] else ""} }}
.no {{ font-size: 28px; font-weight: 700; letter-spacing: 2px; opacity: .65; margin-bottom: 18px; }}
h1 {{ font-size: {lay['titleSize']}px; line-height: 1.22; margin: 0 0 22px; font-weight: 800; word-break: keep-all; overflow-wrap: anywhere; letter-spacing: -1px; }}
.key {{ font-size: {lay['keySize']}px; line-height: 1.35; font-weight: 700; margin: 0 0 18px; word-break: keep-all; overflow-wrap: anywhere; }}
p {{ font-size: {lay['bodySize']}px; line-height: 1.55; margin: 0 0 8px; word-break: keep-all; overflow-wrap: anywhere; opacity: .92; }}
.foot {{ position: absolute; right: 36px; bottom: 28px; font-size: 22px; color: #fff; background: rgba(0,0,0,.38); padding: 6px 14px; border-radius: 99px; }}
</style></head><body><div class="card">
<img id="bg" src="{image_src}" alt="">
<div class="text"><div class="no">{card['no']} / {total}</div><h1>{html.escape(t['title'])}</h1>
<div class="key">{html.escape(t['keyLine'])}</div>{body}</div>
<div class="foot">{html.escape(TOOL_NOTE.get(tool, "생성 그림"))}</div>
</div>{script}</body></html>"""


class Renderer:
    def __init__(self, store, chrome_path=None):
        self.store = store
        self.chrome = find_chrome(chrome_path)

    def cards_dir(self, project_id):
        d = self.store.data_dir / "projects" / project_id / "cards"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def run(self, project_id, run_id, card_nos, emit, cancel):
        if not self.chrome:
            return {"type": "error", "code": "renderer_unavailable",
                    "message": "Chrome 또는 Edge를 찾지 못해 카드를 만들 수 없습니다."}
        doc = self.store.get(project_id)
        sb = doc["storyboard"]
        made = warned = failed = 0
        for no in card_nos:
            if cancel.is_set():
                raise Cancelled()
            card = next(c for c in sb["cards"] if c["no"] == no)
            img = card.get("image") or {}
            if img.get("status") != "done":
                rec = {"status": "failed", "error": "그림이 아직 없습니다.", "at": now_iso()}
            else:
                rec = self.render_one(doc, card, len(sb["cards"]), sb.get("style") or {})
            self._set_card(project_id, run_id, no, rec)
            if rec["status"] != "done":
                failed += 1
                emit(f"카드 {no} 만들기 실패: {rec['error']}")
            else:
                made += 1
                issues = check_issues(rec["checks"])
                warned += bool(issues)
                emit(f"카드 {no} 완성: {rec['file']}" + (f" ⚠ {', '.join(issues)}" if issues else " (검사 통과)"))
        return {"type": "result", "render": {"made": made, "warned": warned, "failed": failed}}

    def render_one(self, doc, card, total, style):
        img = card["image"]
        src_path = self.store.data_dir / "projects" / doc["id"] / "images" / img["file"]
        mime = MIME.get(src_path.suffix.lower(), "image/png")
        data_uri = f"data:{mime};base64," + base64.b64encode(src_path.read_bytes()).decode()
        work = self.store.data_dir / "engine-work" / doc["id"] / "render"
        work.mkdir(parents=True, exist_ok=True)
        page = work / f"card-{card['no']:02d}.html"
        version = int((card.get("render") or {}).get("version") or 0) + 1
        out = self.cards_dir(doc["id"]) / f"card-{card['no']:02d}-r{version}.png"
        # 사용자가 글자 모양을 정했으면 그대로, 아니면 자동 맞춤 후보를 차례로 시도한다
        candidates = [card_layout(card)] if card.get("layout") else AUTO_LAYOUTS
        try:
            for i, lay in enumerate(candidates):
                page.write_text(card_html(card, total, style, data_uri, img.get("tool"), layout=lay), encoding="utf-8")
                checks = self._checks(page, work)
                if not check_issues(checks):
                    break
            checks["autoFit"] = None if card.get("layout") else i + 1
            self._shot(page, out, work)
            info = verify_image(out)
            if (info.get("width"), info.get("height")) != (W, H):
                raise ValueError(f"크기가 {info.get('width')}×{info.get('height')}입니다.")
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            return {"status": "failed", "error": f"렌더링 실패: {exc}", "at": now_iso(), "version": version}
        return {"status": "done", "version": version, "file": out.name, "format": info["format"],
                "width": info["width"], "height": info["height"], "checks": checks,
                "imageFile": img["file"], "text": card_text(card), "layout": card.get("layout"), "usedLayout": lay,
                "at": now_iso()}

    def _chrome(self, work, *args):
        base = [self.chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                "--no-default-browser-check", f"--user-data-dir={work / 'chrome-profile'}",
                f"--window-size={W},{H}", "--virtual-time-budget=4000", "--allow-file-access-from-files"]
        return subprocess.run(base + list(args), capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=90)

    def _checks(self, page, work):
        out = self._chrome(work, "--dump-dom", page.resolve().as_uri())
        m = re.search(r'data-checks="([^"]*)"', out.stdout)
        if not m:
            raise ValueError("페이지 검사 결과를 읽지 못했습니다.")
        return json.loads(html.unescape(m.group(1)))

    def _shot(self, page, out, work):
        if out.exists():
            out.unlink()
        self._chrome(work, f"--screenshot={out}", page.resolve().as_uri())
        if not out.exists():
            raise ValueError("Chrome이 PNG를 만들지 않았습니다.")

    def _set_card(self, project_id, run_id, no, rec):
        def fn(doc):
            run = find_run(doc, run_id)
            if run is None or run["status"] != "running" or doc.get("currentRunId") != run_id:
                raise Cancelled()
            for c in doc["storyboard"]["cards"]:
                if c["no"] == no:
                    c["render"] = rec

        self.store.update(project_id, fn)


def check_issues(checks):
    issues = []
    if checks.get("overflow"):
        issues.append(f"글자가 그림 여백을 넘침({checks.get('textBottom')}px > {checks.get('limit')}px)")
    if checks.get("wideWord"):
        issues.append("한 줄에 안 들어가는 긴 단어")
    if checks.get("lowContrast"):
        issues.append(f"글자가 그림과 겹치거나 대비가 낮음(대비 {checks.get('contrast')}:1, 겹친 부분 {checks.get('overlapPct')}%)")
    if checks.get("smallOnPhone"):
        issues.append(f"휴대폰에서 본문이 작음({checks.get('phoneBodyPx')}px)")
    return issues


def render_stale(card):
    """그림이나 글자가 바뀌어 다시 그려야 하는지."""
    r = card.get("render") or {}
    img = card.get("image") or {}
    if r.get("status") != "done":
        return True
    return r.get("imageFile") != img.get("file") or r.get("text") != card_text(card) or r.get("layout") != card.get("layout")
