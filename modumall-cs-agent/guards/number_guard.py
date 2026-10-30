"""7강: 답변 속 숫자가 근거(매뉴얼·도구 반환값·질문)에 있는지 역추적한다."""
import re

# 숫자 뒤에 한국어 단위(만·천)가 붙으면 곱해서 읽는다: "5만 원" → 50000
_NUMBER = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(만|천)?")
_UNIT = {"만": 10000, "천": 1000}


def _normalize(digits: str, unit: str | None) -> str:
    value = float(digits.replace(",", "").rstrip(".")) * _UNIT.get(unit, 1)
    return str(int(value)) if value.is_integer() else str(value)


def extract_numbers(text: str) -> set[str]:
    """'3,000원', '5만 원', '1~2영업일' 같은 표현에서 숫자를 뽑아 같은 형식의 문자열로 돌려준다."""
    return {_normalize(digits, unit) for digits, unit in _NUMBER.findall(text)}


def check_numbers(answer: str, sources: list[str]) -> tuple[bool, list[str]]:
    """(통과 여부, 출처를 찾지 못한 숫자 목록).

    계산해서 나온 숫자(예: 12900 x 2)도 출처가 없으면 걸린다. 의도된 엄격함이다.
    """
    allowed: set[str] = set()
    for source in sources:
        allowed |= extract_numbers(source)
    unsupported = sorted(extract_numbers(answer) - allowed, key=float)
    return not unsupported, unsupported
