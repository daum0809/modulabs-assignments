# 모두몰 고객 응대 에이전트 구축 파이프라인

> 이 폴더는 수업 과제(제출본: GitHub modulabs-assignments/modumall-cs-agent)다. 과제 설명과 학원 버전으로 바꾸는 방법은 `과제안내.md`.
> 실행은 이 폴더에서 `..\.venv\Scripts\python …`.

LangGraph로 가상 쇼핑몰 '모두몰'의 고객 문의를 유형별로 자동 분류하고, 어드민 시스템에서 필요한 데이터를 조회한 뒤, 엄격한 업무 매뉴얼에 근거해 환각(Hallucination) 없이 답변을 생성하는 파이프라인을 만든다.

## 1. 아키텍처 개요

```
START → route ─┬─(확신도 ≥ 임계값)→ answer → guard ─┬─(통과)→ END
               └─(확신도 < 임계값)→ escalate        └─(실패)→ escalate
```

| 노드 | 역할 |
|---|---|
| `route` | 문의 유형(배송, 반품, 세트 상품 등)을 구조화된 출력(Structured Output)으로 분류하고 확신도를 함께 낸다 |
| `answer` | 라우트별 업무 매뉴얼과 어드민/DB 조회 도구로 정책에 맞는 답변을 생성한다 |
| `guard` | 답변 속 숫자(배송비, 기간, 가격 등)가 조회 데이터나 매뉴얼 원문에 근거하는지 역추적해 검사한다 |
| `escalate` | 확신도가 낮거나 애매한 문의, 가드 검증 실패 건을 사람 상담원에게 넘긴다 |

## 2. 코드 구조 원칙

부품별로 모듈을 나눠 각각 따로 평가·교체할 수 있게 한다.

```
config.py        # 라우트 목록, 확신도 임계값, 모델 이름
state.py         # AgentState (그래프 공유 상태)
llm.py           # LLM 생성 (MODUMALL_MODEL 환경변수)
routers/         # rule_router.py(3강 기준선), llm_router.py(4강 구조화 출력)
tools/           # admin.py(5강 조회 도구, 지금은 JSON 가짜 DB), manuals.py
guards/          # number_guard.py(7강 숫자 출처 검사)
graph.py         # 노드·조건부 에지·컴파일 (8강), CLI 진입점
eval/            # metrics.py, score_router.py, score_pipeline.py
data/            # manuals/*.md, admin_db.json, eval_set.jsonl
tests/           # unittest
```

- 규칙 라우터, 가드, 채점 지표는 표준 라이브러리만 쓴다. API 키 없이 돌아가야 한다.
- 답변에 넣는 매뉴얼은 해당 라우트 것 하나뿐이다. 다른 라우트 정책을 섞지 않는다.
- 가드의 근거(`sources`)는 매뉴얼 원문, 도구 반환 JSON, 고객 질문이다. 계산으로 나온 숫자는 출처가 없으면 걸린다.

## 실행

```bash
uv venv .venv && uv pip install -p .venv -r requirements.txt   # Windows에서는 .venv\Scripts\python 으로 실행
python -m unittest discover -s tests -t .      # 키 불필요 (test_graph는 가짜 LLM 사용)
python -m eval.score_router --router rule      # 키 불필요
# .env.example을 .env로 복사하고 ANTHROPIC_API_KEY 입력
python -m eval.score_router --router llm
python graph.py "MD-1001 언제 와요?"
python -m eval.score_pipeline --router llm
```

## 3. 커리큘럼 (1~9강)

### 1강. 들어가며 (Overview)
- **목표**: 고객 응대 에이전트가 왜 필요한지 이해하고 전체 파이프라인 구조를 파악한다.
- 단일 프롬프트의 한계: 비용 증가, 관련 없는 정책 혼입, 환각 발생
- 4개 핵심 노드(`route`, `answer`, `guard`, `escalate`)와 State 구조 설계 기초

### 2강. 데이터와 라우트 체계, 평가셋 정하기 (Routing & Evaluation Set)
- **목표**: 상담 데이터와 업무 매뉴얼에 근거해 라우트 체계를 세우고 평가셋을 고정한다.
- 모두몰 고객 상담 데이터를 분석해 주요 문의 유형 정의
- 모델 성능 평가용 고정 평가셋(Evaluation Set) 구성

### 3강. 규칙 라우터로 기준선 잡고 점수 읽기 (Rule-based Router)
- **목표**: 규칙 기반 라우터로 기준선(Baseline) 성능을 측정한다.
- 키워드 매칭과 정규식으로 초기 라우터 구현
- Macro F1 Score와 혼동 행렬(Confusion Matrix)로 분류 성능 분석

### 4강. LLM 라우터와 확신도 기반 이관 (LLM Router & Escalation)
- **목표**: 구조화된 출력과 확신도(Confidence) 임계값에 따른 이관을 구현한다.
- Pydantic 등으로 LLM의 구조화된 출력 강제
- 확신도가 임계값 미만이면 `escalate`로 분기하는 조건부 에지(Conditional Edge) 설정

### 5강. 매뉴얼에서 조회 범위 정하고 도구 만들기 (Tool Definition)
- **목표**: 업무 매뉴얼을 기준으로 조회 범위를 정하고 도구(Tool)를 정의한다.
- 라우트별로 필요한 어드민 데이터 정의 (예: 주문 조회, 배송비 조회)
- LLM이 필요한 시점에 스스로 호출할 수 있도록 도구 함수 스키마 작성

### 6강. 근거 기반 답변과 도구 호출 (Grounded Answer Generation)
- **목표**: 조회된 데이터와 매뉴얼에만 엄격히 근거한 답변을 만든다.
- 도구 호출 결과와 업무 매뉴얼로 프롬프트 그라운딩(Grounding)
- 외부 지식이 아닌 조회 데이터에만 의존하도록 시스템 프롬프트 제약 설정

### 7강. 가드레일로 출처 없는 숫자 잡기 (Guardrails & Numerical Verification)
- **목표**: 답변 속 숫자의 출처를 역추적하는 가드레일 노드를 구현한다.
- 답변에서 수치(금액, 일수 등) 추출
- 도구가 반환한 데이터나 매뉴얼 원문과 정확히 일치하는지 검증하는 `guard` 노드 개발

### 8강. 정답셋 채점과 전체 그래프 연결 (Scoring & Graph Integration)
- **목표**: 정답셋으로 채점하고 LangGraph 전체 파이프라인을 통합한다.
- 그래프 컴파일: `START` → `route` → `answer` → `guard` → (`END` 또는 `escalate`)
- 정답셋 기반 자동 채점 루프 구현 및 부품별 에러 원인 진단

### 9강. 정리와 회고 (Review & Retrospective)
- **목표**: 구축 경험을 정리하고 확장 방안을 논의한다.
- 전체 아키텍처 복기
- 실무 적용 시 고려사항: 비동기 처리, 로그 모니터링 등
