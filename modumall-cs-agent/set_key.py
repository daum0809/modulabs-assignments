"""API 키를 화면에 보이지 않게 입력받아 .env 첫 줄에 저장한다.

실행: .venv\\Scripts\\python set_key.py
"""
import getpass
import os
import re
from pathlib import Path

ENV = Path(__file__).parent / ".env"

os.system("")  # Windows 콘솔에서 ANSI 색 켜기
YELLOW, GREEN, RED, CYAN, BOLD, RESET = "\033[93m", "\033[92m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
BOX = "\033[30;103m"  # 노란 배경 검정 글씨

print()
print(f"{YELLOW}{'=' * 60}{RESET}")
print(f"{BOLD}  Anthropic API 키 입력{RESET}")
print(f"  - {CYAN}sk-ant-api03-{RESET} 로 시작하는 100자 넘는 키여야 합니다")
print(f"  - 붙여 넣으면 키 대신 {BOLD}*****{RESET} 별표가 찍힙니다")
print(f"{YELLOW}{'=' * 60}{RESET}")
print()
print(f"{GREEN}{BOLD}  ▼▼▼ 바로 아래 노란 칸 옆에 Ctrl+V 로 붙여 넣고 Enter ▼▼▼{RESET}")
print()

def read_masked(prompt: str) -> str:
    """입력한 글자마다 *를 찍어 붙여넣기가 됐는지 보이게 한다 (Windows 콘솔 전용)."""
    try:
        import msvcrt
    except ImportError:
        return getpass.getpass(prompt)
    print(prompt, end="", flush=True)
    chars: list[str] = []
    while True:
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            print()
            return "".join(chars)
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch == "\x08":
            if chars:
                chars.pop()
                print("\b \b", end="", flush=True)
            continue
        chars.append(ch)
        print("*", end="", flush=True)


key = read_masked(f"  {BOX} 여기에 붙여넣기 → {RESET} ").strip()

print()
# 형식만 대략 본다. 실제로 쓸 수 있는지는 API 호출로 확인한다.
if not re.fullmatch(r"sk-ant-[A-Za-z0-9_-]{40,}", key):
    print(f"{RED}{BOLD}  ✗ API 키 형식이 아닙니다{RESET} (길이 {len(key)}, 앞부분 {key[:10]!r})")
    print("    console.anthropic.com > API Keys > Create Key 직후 창에서 Copy한")
    print(f"    {CYAN}sk-ant-api03-...{RESET} 키를 넣어 주세요.")
    input("\n  Enter를 누르면 끝납니다...")
    raise SystemExit(1)

lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
lines = [line for line in lines if not line.startswith("ANTHROPIC_API_KEY=")]
ENV.write_text("\n".join([f"ANTHROPIC_API_KEY={key}", *lines]) + "\n", encoding="utf-8")
print(f"{GREEN}{BOLD}  ✓ 저장했습니다{RESET} (키 길이 {len(key)}자). Claude에게 '실행해줘'라고 말씀해 주세요.")
