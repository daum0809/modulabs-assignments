"""검색(Retrieval) 품질 평가: 질문마다 정답 문서가 상위 k개 안에 들어오는지 측정한다.

  python cli.py ingest sample_docs/*.md
  python eval.py

키워드(BM25)만 쓸 때와 하이브리드(BM25 + 임베딩)를 비교해 출력한다.
"""
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app import rag, store  # noqa: E402

CASES = json.loads(Path(__file__).with_name("eval_questions.json").read_text(encoding="utf-8"))


def evaluate(label):
    hit1 = hit3 = rr = 0.0
    misses = []
    for case in CASES:
        titles = [h["title"] for h in rag.index.search(case["question"], k=5)]
        rank = titles.index(case["expected"]) + 1 if case["expected"] in titles else None
        hit1 += rank == 1
        hit3 += rank is not None and rank <= 3
        rr += 1 / rank if rank else 0
        if rank != 1:
            misses.append((case["question"], case["expected"], titles[:3]))
    n = len(CASES)
    print(f"[{label}] Hit@1 {hit1 / n:.0%} · Hit@3 {hit3 / n:.0%} · MRR {rr / n:.3f}  (질문 {n}개)")
    for q, exp, got in misses:
        print(f"   ✗ {q}  → 정답 '{exp}', 검색 {got}")


def main():
    store.init()
    rag.index.rebuild()
    full = rag.index.matrix
    rag.index.matrix = None
    evaluate("키워드(BM25)")
    if full is not None:
        rag.index.matrix = full
        evaluate("하이브리드(BM25+임베딩)")
    else:
        print("(임베딩을 쓸 수 없어 하이브리드 평가는 건너뜀: ollama pull bge-m3)")


if __name__ == "__main__":
    main()
