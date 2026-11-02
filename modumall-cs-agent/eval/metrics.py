"""3강: 정확도, Macro F1, 혼동 행렬 (외부 라이브러리 없이)."""
import json

import config

SETS = {"dev": config.EVAL_SET_PATH, "test": config.TEST_SET_PATH}


def load_eval_set(name: str = "dev") -> list[dict]:
    """dev = 개발셋(튜닝하며 본 문항), test = 테스트셋(튜닝에 쓰지 않은 문항)."""
    with open(SETS[name], encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def accuracy(y_true: list[str], y_pred: list[str]) -> float:
    return sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true)


def macro_f1(y_true: list[str], y_pred: list[str], labels=config.ROUTES) -> tuple[float, dict]:
    per_label = {}
    for label in labels:
        tp = sum(t == label and p == label for t, p in zip(y_true, y_pred))
        fp = sum(t != label and p == label for t, p in zip(y_true, y_pred))
        fn = sum(t == label and p != label for t, p in zip(y_true, y_pred))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    # 평가셋에 정답이 하나도 없는 라벨은 평균에서 뺀다
    scored = [v["f1"] for v in per_label.values() if v["support"]]
    return sum(scored) / len(scored), per_label


def confusion_matrix_text(y_true: list[str], y_pred: list[str], labels=config.ROUTES) -> str:
    width = max(len(label) for label in labels) + 2
    lines = ["true/pred".ljust(width) + "".join(label.rjust(width) for label in labels)]
    for t in labels:
        row = [sum(a == t and b == p for a, b in zip(y_true, y_pred)) for p in labels]
        lines.append(t.ljust(width) + "".join(str(n).rjust(width) for n in row))
    return "\n".join(lines)
