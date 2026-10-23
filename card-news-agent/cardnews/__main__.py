"""실행: python -m cardnews            (실제 엔진: Claude CLI)
       python -m cardnews --engine mock (모의 데이터)"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .engines import ENGINES, make_engine
from .images import ImageMaker
from .jobs import Runner
from .server import App, serve
from .store import Store

KIT_DIR = Path(__file__).resolve().parent.parent


def check_claude_login(exe):
    """claude auth status로 로그인 여부만 확인한다(계정 정보는 출력하지 않음)."""
    from .engines.claude_cli import clean_env

    try:
        out = subprocess.run([exe, "auth", "status"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", env=clean_env(), timeout=60)
        status = json.loads(out.stdout or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {"ready": False, "note": f"Claude CLI 상태를 확인하지 못했습니다: {exc}"}
    if status.get("loggedIn"):
        return {"ready": True, "note": ""}
    return {"ready": False, "note": "Claude CLI에 로그인되어 있지 않습니다. 터미널에서 `claude auth login`으로 로그인한 뒤 앱을 다시 켜세요."}


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m cardnews", description="카드뉴스 워크플로 앱")
    p.add_argument("--engine", default="claude-cli", choices=ENGINES, help="실행 엔진 (기본 claude-cli, 모의는 mock)")
    p.add_argument("--port", type=int, default=8765, help="포트 (기본 8765)")
    p.add_argument("--data-dir", default=str(KIT_DIR / "data"), help="결과 보관 폴더 (기본 data)")
    p.add_argument("--model", default="sonnet", help="claude-cli 모델 (기본 sonnet)")
    p.add_argument("--effort", default="medium", help="claude-cli effort (기본 medium)")
    p.add_argument("--claude-path", default=None, help="claude.exe 경로 (자동으로 못 찾을 때만)")
    p.add_argument("--no-agy", action="store_true", help="그림에 agy를 쓰지 않고 바로 claude cli 도형 그림으로 만든다")
    p.add_argument("--mock-fail", default="", help="시험용(mock): 일부러 실패시킬 작업 (research,editorial,storyboard,image)")
    args = p.parse_args(argv)

    # Windows 콘솔에서도 한글이 깨지지 않게 한다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    host = "127.0.0.1"  # PRD: 내 PC에서만 열리게 한다
    store = Store(args.data_dir)
    fail = {s.strip() for s in args.mock_fail.split(",") if s.strip()}
    try:
        engine = make_engine(args.engine, fail=fail, work_dir=store.data_dir / "engine-work",
                             claude_path=args.claude_path, model=args.model, effort=args.effort)
    except FileNotFoundError as exc:
        print(f"실행 엔진을 준비하지 못했습니다: {exc}")
        print("모의 데이터로 화면만 보려면: python -m cardnews --engine mock")
        return 1
    status = check_claude_login(engine.exe) if args.engine == "claude-cli" else None
    interrupted = store.mark_interrupted()
    images = ImageMaker(store, engine, use_agy=args.engine != "mock" and not args.no_agy)
    runner = Runner(store, engine, images)
    app = App(store, runner, engine.name, status)

    try:
        httpd = serve(app, host, args.port)
    except OSError:
        print(f"포트 {args.port}을(를) 이미 다른 프로그램이 쓰고 있습니다.")
        print(f"다른 포트로 켜 보세요: python -m cardnews --engine {args.engine} --port {args.port + 2}")
        return 1

    print("=" * 56)
    print(f" 카드뉴스 앱이 켜졌습니다:  http://{host}:{args.port}")
    if engine.name == "mock":
        print(" 실행 엔진: mock  (모의 데이터 — 실제 조사 아님)")
    else:
        print(f" 실행 엔진: Claude CLI ({args.model}, effort {args.effort})")
        print(f"   {engine.exe}")
        print(" 로그인: " + ("확인됨" if status["ready"] else "⚠ " + status["note"]))
    if engine.name != "mock":
        if images.use_agy:
            print(f" 그림: agy {'(' + images.agy + ')' if images.agy else '없음'} → 안 되면 claude cli 도형 그림")
        else:
            print(" 그림: claude cli 도형 그림 (--no-agy)")
    print(f" 결과 보관 폴더: {store.data_dir}")
    if fail:
        print(f" 시험용 모의 실패: {', '.join(sorted(fail))}")
    if interrupted:
        print(f" 이전 실행에서 중단된 프로젝트 {len(interrupted)}개를 '중단됨'으로 표시했습니다.")
    print(" 끄려면 이 창에서 Ctrl + C 를 누르세요.")
    print("=" * 56)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 끄는 중입니다. 실행 중인 엔진 작업도 정리합니다.")
    finally:
        runner.shutdown()
        httpd.server_close()
        print("서버를 껐습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
