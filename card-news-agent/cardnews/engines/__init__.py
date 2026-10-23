"""실행 엔진.

앱은 엔진을 아래 두 작업으로만 부른다. 엔진이 무엇이든 결과는
need_input / result / error 중 하나의 dict로 돌려준다(진행 상황은 emit으로).

- research(ctx, emit, cancel): 넓은 조사 → {"type": "result", "research": {...}}
- editorial(ctx, emit, cancel): 심층 조사·편집 판단 →
  {"type": "need_input", "question": {...}} 또는 {"type": "result", "editorial": {...}}

ctx에는 프로젝트의 주제·자료 위치·편집 방향·선택한 후보·지금까지의 답변과
엔진 세션 ID가 들어 있다. 엔진은 한 번 호출이 끝나면 멈춰도 된다.
답변을 받으면 앱이 같은 세션 ID와 답변을 담아 다시 부른다.
결과에 "sessionId"가 있으면 앱이 그 프로젝트의 세션 ID로 저장한다.
"""

from .mock import MockEngine

ENGINES = ["claude-cli", "mock"]


def make_engine(name, **options):
    if name == "mock":
        return MockEngine(fail=options.get("fail"), step_seconds=options.get("step_seconds", 0.8))
    if name == "claude-cli":
        from .claude_cli import ClaudeCliEngine

        return ClaudeCliEngine(**options)
    raise ValueError(f"알 수 없는 엔진: {name} (가능: {', '.join(ENGINES)})")
