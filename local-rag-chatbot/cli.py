"""명령줄 도구.

  python cli.py ingest sample_docs/*.md     문서 등록 (같은 제목은 교체)
  python cli.py search "보강 신청 기한"       검색 결과만 보기
  python cli.py ask "결석하면 어떻게 하나요?"  RAG 답변
"""
import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app import chat, rag, store  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="로컬 RAG 챗봇 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest").add_argument("files", nargs="+")
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=5)
    sub.add_parser("ask").add_argument("question")
    args = p.parse_args()

    store.init()
    rag.index.rebuild()

    if args.cmd == "ingest":
        for f in args.files:
            path = Path(f)
            title = path.stem
            if (old := store.find_document(title)) is not None:
                store.delete_document(old)
            text = rag.extract_text(path.name, path.read_bytes())
            rag.ingest(title, text)
            print(f"등록: {title}")
    elif args.cmd == "search":
        for i, h in enumerate(rag.index.search(args.query, k=args.k), 1):
            print(f"{i}. [{h['title']}] score={h['score']}\n   {h['text'][:100]}…")
    else:
        r = chat.answer(args.question)
        print(r["answer"])
        if r["sources"]:
            print("\n출처:", ", ".join(r["sources"]))


if __name__ == "__main__":
    main()
