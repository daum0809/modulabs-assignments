# 모두몰 고객 응대 에이전트

가상 쇼핑몰 '모두몰'의 고객 문의를 LangGraph로 처리하는 파이프라인입니다. 문의를 유형별로 나누고, 주문 정보를 조회한 뒤, 업무 매뉴얼에 근거한 답변만 내보냅니다. 근거가 없는 숫자가 섞이거나 애매한 문의는 사람 상담원에게 넘깁니다.

```
START → route ─┬─(확신도 ≥ 0.7)→ answer → guard ─┬─(통과)→ END
               └─(확신도 < 0.7)→ escalate       └─(실패)→ escalate
```

| 노드 | 하는 일 |
|---|---|
| `route` | 문의를 배송·반품·세트 상품·주문·기타로 분류하고 확신도를 매긴다 |
| `answer` | 해당 라우트의 매뉴얼과 주문 조회 도구만 써서 답변한다 |
| `guard` | 답변 속 숫자가 매뉴얼·조회 결과·질문에 있는지 역추적한다 (`5만 원` → 50000 처럼 단위도 읽음) |
| `escalate` | 확신도가 낮거나 가드를 통과 못 한 답변을 상담원에게 넘긴다 |

## 결과

개발셋(`data/eval_set.jsonl`, 14문항)은 튜닝하며 본 문항, 테스트셋(`data/test_set.jsonl`, 12문항)은 튜닝에 쓰지 않은 문항입니다.

| | 개발셋 | 테스트셋 |
|---|---|---|
| 규칙 라우터 정확도 / Macro F1 | 0.857 / 0.836 | 0.833 / 0.820 |
| LLM 라우터 정확도 / Macro F1 | 0.857 / 0.836 | 1.000 / 1.000 |
| 이관 판정 일치 (규칙 → LLM) | 9 → 13 / 14 | 8 → 11 / 12 |
| 전체 파이프라인 (답변 품질 기준 R1~R5 모두 통과) | **12/14** | **12/12** |

- 답변 품질 기준: `eval/answer_rubric.py` (분류, 이관, 필수정보, 정책 혼입 없음, 근거 있는 숫자)
- 채점기 타당성: 사람이 판정한 예시 10개와 50/50 일치 (`python -m eval.validate_scorer`)
- 실패 분석: [실패분석.md](실패분석.md), 카테고리 설계와 근거 매핑: [과제안내.md](과제안내.md)

개발셋으로 전체 파이프라인을 9/14 → 11/14 → 12/14로 고친 과정:
1. 도구 설명의 예시 주문번호(`MD-1001`)를 모델이 고객에게 그대로 안내 → 가드가 차단. 도구 설명에서 숫자 예시를 뺐다.
2. "배송지 변경"을 배송으로 분류 → 라우터 프롬프트에 order 규칙 추가.
3. 가드가 "5만 원"과 매뉴얼의 "50,000원"을 다른 숫자로 봄 → 만·천 단위 해석 추가.
4. 모델이 "3,000원 + 3,000원 = 총 6,000원"처럼 합계를 만들어 가드에 걸림 → 가드는 엄격하게 두고 답변 프롬프트에서 합계 계산을 금지.

남은 2건: q08(분류는 맞았지만 확신도 0.6으로 과잉 이관), q14(반품과 세트 상품이 섞인 복합 문의, 안전하게 이관).

## 실행

```bash
uv venv .venv && uv pip install -p .venv -r requirements.txt
python -m unittest discover -s tests -t .                  # 테스트 18개, API 키 불필요 (그래프 테스트는 가짜 LLM)
python -m eval.validate_scorer                             # 채점기 타당성, API 키 불필요
python -m eval.score_router --router rule --set test       # API 키 불필요
python set_key.py                                          # API 키를 화면에 안 보이게 입력해 .env에 저장
python -m eval.score_router --router llm --set test
python -m eval.score_pipeline --router llm --set test      # 답변 전문은 eval/results/test.jsonl
python graph.py "MD-1001 언제 와요?"
```

데이터(매뉴얼, 주문 3건, 평가셋)는 모두 연습용 가상 데이터입니다. 구조와 강의별 대응은 [CLAUDE.md](CLAUDE.md)에 있습니다.
