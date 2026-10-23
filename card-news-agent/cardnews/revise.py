"""요청문으로 카드 고치기 (STEP 9).

고를 카드와 요청문을 받아 그 카드만 고친다.
- scope "text": 엔진이 글만 고치고, 그림은 그대로 둔 채 그 카드만 다시 그린다.
- scope "image": 그림 요청에 수정 사항을 붙여 그 카드 그림만 다시 만들고 다시 그린다.
고치지 않은 카드는 건드리지 않는다. 최종 승인은 카드가 바뀌면 자동으로 풀린다(exports.final_ok).
"""

from .engines.mock import Cancelled
from .render import card_text
from .store import find_run, now_iso


class Reviser:
    def __init__(self, store, engine, images, renderer):
        self.store = store
        self.engine = engine
        self.images = images
        self.renderer = renderer

    def run(self, project_id, run_id, card_nos, emit, cancel):
        doc = self.store.get(project_id)
        run = find_run(doc, run_id)
        instruction, scope = run.get("instruction", ""), run.get("scope", "text")
        sb = doc["storyboard"]
        total = len(sb["cards"])
        done = failed = 0
        for no in card_nos:
            if cancel.is_set():
                raise Cancelled()
            doc = self.store.get(project_id)
            card = next(c for c in doc["storyboard"]["cards"] if c["no"] == no)
            if scope == "image":
                card["imageNote"] = instruction
                prev = card.get("image") or {}
                agy_state = self.images.check_agy(emit)
                rec = self.images._make_one(doc, card, sb.get("style") or {}, prev, agy_state, emit, cancel)
                if rec["status"] != "done":
                    failed += 1
                    emit(f"카드 {no} 그림 고치기 실패: {rec.get('error')} — 이전 그림을 그대로 둡니다.")
                    self._update_card(project_id, run_id, no, {"revision": self._log(card, instruction, scope, rec.get("error"))})
                    continue
                self._update_card(project_id, run_id, no, {"image": rec, "imageNote": instruction})
                emit(f"카드 {no} 그림을 고쳤습니다: {rec['file']} ({rec['toolLabel']})")
            else:
                res = self.engine.revise_text({"projectId": project_id, "editorial": doc.get("editorial")},
                                              card, card_text(card), instruction, emit, cancel)
                if res["type"] != "ok":
                    failed += 1
                    emit(f"카드 {no} 글 고치기 실패: {res.get('message')}")
                    self._update_card(project_id, run_id, no, {"revision": self._log(card, instruction, scope, res.get("message"))})
                    continue
                self._update_card(project_id, run_id, no, {"text": res["text"]})
                emit(f"카드 {no} 글을 고쳤습니다: {res.get('note') or ''}")
            doc = self.store.get(project_id)
            card = next(c for c in doc["storyboard"]["cards"] if c["no"] == no)
            rec = self.renderer.render_one(doc, card, total, doc["storyboard"].get("style") or {})
            self._update_card(project_id, run_id, no, {"render": rec, "revision": self._log(card, instruction, scope, None)})
            if rec["status"] == "done":
                done += 1
            else:
                failed += 1
        return {"type": "result", "revise": {"done": done, "failed": failed, "scope": scope}}

    def _log(self, card, instruction, scope, error):
        history = list((card.get("revision") or {}).get("history", []))
        history.append({"at": now_iso(), "instruction": instruction, "scope": scope, "error": error})
        return {"history": history}

    def _update_card(self, project_id, run_id, no, fields):
        def fn(doc):
            run = find_run(doc, run_id)
            if run is None or run["status"] != "running" or doc.get("currentRunId") != run_id:
                raise Cancelled()
            for c in doc["storyboard"]["cards"]:
                if c["no"] == no:
                    c.update(fields)

        self.store.update(project_id, fn)
