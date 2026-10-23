"""최종 승인과 내보내기 (STEP 9).

- 최종 승인은 '그 순간의 카드 PNG와 글' 묶음(signature)에 대해 저장한다. 카드가 하나라도 바뀌면 승인이 풀린 것으로 본다.
- 내보내기는 최종 승인된 묶음만: 카드 PNG, 출처 기록, 이미지 사용 기록을 ZIP 하나로.
- 앱의 PNG는 초안이다. 디자인은 Canva 템플릿에서 마무리하므로 카드별 글을 'Canva용 글.md'로 함께 넣는다.
- 검증은 내보낸 ZIP 파일 자체를 열어 확인한다. 기계로 확인할 수 없는 것은 통과로 적지 않고 '사람이 확인'으로 남긴다.
"""

import hashlib
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

from .images import verify_image
from .render import H, W, card_text, check_issues, render_stale
from .rules import text_warnings
from .store import now_iso


def signature(doc):
    cards = (doc.get("storyboard") or {}).get("cards", [])
    raw = json.dumps([[c["no"], (c.get("render") or {}).get("file"), card_text(c)] for c in cards], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def ready_for_final(doc):
    """최종 승인할 수 있는 상태인지와, 아니라면 이유."""
    sb = doc.get("storyboard") or {}
    cards = sb.get("cards", [])
    if not sb.get("approved") or not cards:
        return False, "스토리보드 승인과 카드가 필요합니다."
    missing = [c["no"] for c in cards if (c.get("render") or {}).get("status") != "done" or render_stale(c, len(cards))]
    if missing:
        return False, f"아직 최신 카드가 아닌 카드: {', '.join(map(str, missing))} (카드 만들기를 먼저 하세요)"
    return True, ""


def final_ok(doc):
    fa = doc.get("finalApproval")
    return bool(fa) and fa.get("signature") == signature(doc) and ready_for_final(doc)[0]


def _rel(path, source_root):
    """출처의 PC 경로를 자료 폴더 기준 상대 경로로 바꾼다(내보낸 파일에 PC 경로를 남기지 않음)."""
    s = str(path)
    if source_root and s.lower().startswith(str(source_root).lower()):
        return Path(source_root).name + s[len(str(source_root)):].replace("\\", "/")
    return s


def build_zip(doc, data_dir):
    pid = doc["id"]
    sb = doc["storyboard"]
    cards = sb["cards"]
    research = doc.get("research") or {}
    ed = doc.get("editorial") or {}
    src_root = doc.get("sourcePath")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(data_dir) / "projects" / pid / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"cardnews-{stamp}.zip"

    sources = ["# 출처 기록", "",
               f"- 주제: {doc['topic']}",
               f"- 조사 기준 시각: {research.get('researchedAt', '미확인')}",
               f"- 조사 기간: {research.get('periodStart', '?')} ~ {research.get('periodEnd', '?')}",
               f"- 자료 위치: {Path(src_root).name if src_root else '웹 조사'} (자료 폴더 기준 상대 경로로 표기)",
               f"- 독자: {ed.get('audience', '')}",
               f"- 최종 승인: {doc['finalApproval']['at']}",
               ""]
    for c in cards:
        t = card_text(c)
        sources += [f"## 카드 {c['no']} — {t['title']}", f"- 핵심 문장: {t['keyLine']}"]
        if t["body"]:
            sources.append(f"- 본문: {t['body']}")
        sources += [f"- 근거: {_rel(s, src_root)}" for s in c.get("sources", [])] or ["- 근거: (없음 — 확인 필요)"]
        sources.append("")
    v = ed.get("verification") or {}
    for title, key in (("확인한 사실", "facts"), ("발표 주체·운영자의 주장", "claims"), ("아직 확인하지 못한 것", "unknown")):
        sources.append(f"## 심층 검증: {title}")
        sources += [f"- {x.get('text')} — {_rel(x.get('source', ''), src_root)}" for x in v.get(key, [])] or ["- 없음"]
        sources.append("")

    log = []
    lines = ["# 이미지 사용 기록", "", "모든 그림은 생성 이미지입니다. 실제 프로그램 화면이나 사진이 아닙니다.", ""]
    for c in cards:
        img = c.get("image") or {}
        entry = {"card": c["no"], "cardFile": f"cards/{c['no']:02d}.png", "imageFile": img.get("file"),
                 "kind": img.get("kind", "생성 이미지"), "tool": img.get("tool"), "toolLabel": img.get("toolLabel"),
                 "createdAt": img.get("createdAt"), "prompt": img.get("prompt"), "fallbackReason": img.get("fallbackReason"),
                 "format": img.get("format"), "width": img.get("width"), "height": img.get("height")}
        log.append(entry)
        lines += [f"## 카드 {c['no']}", f"- 도구: {img.get('toolLabel') or img.get('tool')}", f"- 원본: {img.get('file')} ({img.get('format')} {img.get('width')}×{img.get('height')})",
                  f"- 만든 시각: {img.get('createdAt') or '기록 없음'}", f"- 요청문: {img.get('prompt')}"]
        if img.get("fallbackReason"):
            lines.append(f"- agy 대신 쓴 이유: {img['fallbackReason']}")
        lines.append("")

    canva = ["# Canva용 글", "",
             "앱이 만든 PNG는 초안입니다. 디자인은 Canva 템플릿에 아래 글을 넣어 마무리하세요.",
             f"- 템플릿 페이지를 {len(cards)}장으로 맞춘 뒤, 페이지마다 아래 글을 넣습니다.",
             "- 글은 최종 승인한 그대로입니다. 바꾸면 출처.md의 근거와 다시 대조하세요.",
             "- 템플릿 제작자 문구·예시 그림은 지우거나 내 내용에 맞게 바꿉니다.", ""]
    for c in cards:
        t = card_text(c)
        canva += [f"## {c['no']} / {len(cards)}", f"제목: {t['title']}", f"핵심 문장: {t['keyLine']}"]
        if t["body"]:
            canva.append(f"본문: {t['body']}")
        canva.append("")

    readme = ["# 카드뉴스 내보내기", "", f"- 주제: {doc['topic']}", f"- 카드: {len(cards)}장 (1080×1350 PNG, cards/ 폴더, 순서대로 01~)",
              "- Canva용 글.md: 카드별 글. PNG는 초안이고, 디자인은 Canva 템플릿에서 마무리합니다",
              "- 출처.md: 조사 기준·카드별 근거·심층 검증", "- 이미지기록.md / image-log.json: 그림 도구·요청문·대신한 이유",
              f"- 최종 승인: {doc['finalApproval']['at']} (서명 {doc['finalApproval']['signature']})", ""]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for c in cards:
            z.write(Path(data_dir) / "projects" / pid / "cards" / c["render"]["file"], f"cards/{c['no']:02d}.png")
        z.writestr("출처.md", "\n".join(sources))
        z.writestr("Canva용 글.md", "\n".join(canva))
        z.writestr("이미지기록.md", "\n".join(lines))
        z.writestr("image-log.json", json.dumps(log, ensure_ascii=False, indent=1))
        z.writestr("README.md", "\n".join(readme))
    (out_dir / name).write_bytes(buf.getvalue())
    return {"file": name, "bytes": len(buf.getvalue()), "at": now_iso(), "signature": doc["finalApproval"]["signature"],
            "cards": len(cards)}


def verify_zip(doc, data_dir, name):
    """내보낸 ZIP을 직접 열어 검사한다. 결과: [{item, result: 통과|실패|확인 못 함, detail}]."""
    path = Path(data_dir) / "projects" / doc["id"] / "exports" / name
    cards = doc["storyboard"]["cards"]
    rows = []

    def add(item, ok, detail):
        rows.append({"item": item, "result": ok, "detail": detail})

    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        add("ZIP 열기", "실패", str(exc))
        return rows
    with z:
        names = z.namelist()
        pngs = sorted(n for n in names if n.startswith("cards/") and n.endswith(".png"))
        expect = [f"cards/{c['no']:02d}.png" for c in cards]
        add("카드 수·순서", "통과" if pngs == expect else "실패", f"ZIP {len(pngs)}장 / 카드 {len(cards)}장")
        bad = []
        tmp = path.parent / "_verify"
        tmp.mkdir(exist_ok=True)
        for n in pngs:
            f = tmp / Path(n).name
            f.write_bytes(z.read(n))
            try:
                info = verify_image(f)
                if (info["format"], info["width"], info["height"]) != ("PNG", W, H):
                    bad.append(f"{n} {info['format']} {info['width']}×{info['height']}")
            except ValueError as exc:
                bad.append(f"{n}: {exc}")
        add("PNG 형식·크기 (1080×1350)", "실패" if bad else "통과", "; ".join(bad) or f"{len(pngs)}장 모두 PNG 1080×1350")
        cut = [f"카드 {c['no']}: {', '.join(check_issues(c['render'].get('checks') or {}))}" for c in cards
               if check_issues(c["render"].get("checks") or {})]
        add("글자 잘림·겹침·휴대폰 가독성 (렌더링 때 측정)", "실패" if cut else "통과", "; ".join(cut) or "모든 카드 검사 통과")
        for need in ("출처.md", "이미지기록.md", "image-log.json", "Canva용 글.md"):
            add(f"{need} 포함", "통과" if need in names else "실패", "")
        src = z.read("출처.md").decode("utf-8") if "출처.md" in names else ""
        no_src = [c["no"] for c in cards if not c.get("sources")]
        add("카드마다 근거 표시", "실패" if no_src else "통과", f"근거 없는 카드: {no_src}" if no_src else "모든 카드에 근거 있음")
        add("조사 기준 시각·기간 기록", "통과" if "조사 기준 시각" in src and "미확인" not in src.split("조사 기준 시각:")[1][:12] else "실패", "")
        log = json.loads(z.read("image-log.json")) if "image-log.json" in names else []
        no_tool = [e["card"] for e in log if not e.get("tool")]
        add("카드마다 그림 도구 기록", "실패" if no_tool or len(log) != len(cards) else "통과", f"도구 없는 카드: {no_tool}" if no_tool else "")
        allow = doc.get("direction") or ""
        rule = [f"카드 {c['no']}: {'; '.join(text_warnings(card_text(c), allow))}" for c in cards
                if text_warnings(card_text(c), allow)]
        add("카드 글 규칙 (짧은 글 · 프로그램 내부 비공개)", "실패" if rule else "통과", "; ".join(rule) or "모든 카드가 규칙 안")
        leaked = [n for n in names if b"C:\\Users" in z.read(n) or b"C:/Users" in z.read(n)]
        add("내 PC 경로가 남지 않음", "실패" if leaked else "통과", ", ".join(leaked))
    add("근거 링크가 지금도 열리는지", "확인 못 함", "앱은 링크를 열어 보지 않습니다. 출처.md의 링크를 직접 열어 확인하세요.")
    add("카드 문장이 근거와 같은 뜻인지", "확인 못 함", "사람이 출처.md의 근거와 카드 문장을 대조해야 합니다.")
    add("주휴수당·세금 내용의 정확성", "확인 못 함", "법·세무 판단은 노무사·세무사 확인이 필요합니다.")
    add("휴대폰에서 실제로 넘겨 읽기", "확인 못 함", "PNG를 휴대폰에 옮겨 직접 넘겨 보세요.")
    add("디자인 마무리 (Canva)", "확인 못 함", "앱의 PNG는 초안입니다. 'Canva용 글.md'의 글을 Canva 템플릿에 넣어 디자인을 마무리하세요.")
    return rows
