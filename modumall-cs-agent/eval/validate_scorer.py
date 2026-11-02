"""채점 기준 자체가 타당한지 확인한다.

사람이 미리 판단해 둔 답변 예시(data/scorer_calibration.jsonl)를 채점기에 넣고,
채점기 판정이 사람 판정과 얼마나 일치하는지 본다. 하나라도 어긋나면 채점기를 고친다.

실행: python -m eval.validate_scorer
"""
import json
import sys

import config
from eval.answer_rubric import CRITERIA, grade

CALIBRATION_PATH = config.DATA_DIR / "scorer_calibration.jsonl"


def load():
    with open(CALIBRATION_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def disagreements(items) -> list[tuple[str, str, object, object]]:
    out = []
    for item in items:
        got = grade(item["case"], item["result"])
        for key in CRITERIA:
            if got[key] != item["human"][key]:
                out.append((item["id"], key, item["human"][key], got[key]))
    return out


def main():
    items = load()
    bad = disagreements(items)
    total = len(items) * len(CRITERIA)
    print(f"채점기-사람 판정 일치: {total - len(bad)}/{total}")
    for key, desc in CRITERIA.items():
        n = sum(1 for _, k, _, _ in bad if k == key)
        print(f"  {key:<12} {len(items) - n}/{len(items)}  {desc}")
    for item in items:
        print(f"  {item['id']}: {item['note']}")
    for cid, key, human, got in bad:
        print(f"불일치 {cid} {key}: 사람={human} 채점기={got}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
