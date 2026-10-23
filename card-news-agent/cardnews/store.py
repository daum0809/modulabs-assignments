"""프로젝트 상태 저장소.

프로젝트 하나를 JSON 문서 하나로 SQLite에 저장한다. 서버를 다시 켜도
후보·선택·질문·답변·작업 기록이 남는다.
"""

import json
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path

ACTIVE_STATUSES = {"researching", "running"}
MAX_EVENTS = 200


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class NotFound(Exception):
    pass


class Store:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "cardnews.sqlite3"
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS projects ("
            " id TEXT PRIMARY KEY, created_at TEXT NOT NULL, doc TEXT NOT NULL)"
        )
        self._db.commit()

    def create(self, doc):
        with self._lock:
            self._db.execute(
                "INSERT INTO projects (id, created_at, doc) VALUES (?, ?, ?)",
                (doc["id"], doc["createdAt"], json.dumps(doc, ensure_ascii=False)),
            )
            self._db.commit()
        return doc

    def get(self, project_id):
        with self._lock:
            row = self._db.execute(
                "SELECT doc FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        if row is None:
            raise NotFound(project_id)
        return json.loads(row[0])

    def list(self):
        with self._lock:
            rows = self._db.execute(
                "SELECT doc FROM projects ORDER BY created_at DESC"
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def update(self, project_id, fn):
        """잠금 안에서 문서를 읽고 fn(doc)으로 고친 뒤 저장한다. fn의 반환값을 돌려준다."""
        with self._lock:
            doc = self.get(project_id)
            result = fn(doc)
            doc["rev"] = doc.get("rev", 0) + 1
            doc["updatedAt"] = now_iso()
            doc["events"] = doc.get("events", [])[-MAX_EVENTS:]
            self._db.execute(
                "UPDATE projects SET doc = ? WHERE id = ?",
                (json.dumps(doc, ensure_ascii=False), project_id),
            )
            self._db.commit()
            return result

    def mark_interrupted(self):
        """서버 시작 시: 이전 서버에서 돌던 작업을 '중단됨'으로 바꾼다."""
        changed = []
        for doc in self.list():
            if doc.get("status") not in ACTIVE_STATUSES:
                continue

            def fn(d):
                run = find_run(d, d.get("currentRunId"))
                if run and run["status"] == "running":
                    run["status"] = "interrupted"
                    run["finishedAt"] = now_iso()
                    run["error"] = "서버가 다시 시작되어 작업이 중단되었습니다."
                from .images import mark_interrupted_cards

                mark_interrupted_cards(d)
                d["status"] = "interrupted"
                d["error"] = {
                    "code": "interrupted",
                    "message": "서버가 다시 시작되어 작업이 중단되었습니다. 다시 시도할 수 있습니다.",
                }
                add_event(d, "서버 재시작으로 진행 중이던 작업을 중단됨으로 표시했습니다.")

            self.update(doc["id"], fn)
            changed.append(doc["id"])
        return changed


def add_event(doc, message):
    doc.setdefault("events", []).append({"at": now_iso(), "message": message})


def find_run(doc, run_id):
    for run in doc.get("runs", []):
        if run["id"] == run_id:
            return run
    return None
