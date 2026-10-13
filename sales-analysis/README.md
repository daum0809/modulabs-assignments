# 매출분석 툴

CSV 매출 데이터를 올리면 지표를 계산하고, AI가 결과를 분석해 주는 웹 서비스입니다.

- 숫자는 코드가 계산합니다. AI는 계산된 결과만 받아 해석하고, 숫자를 지어내지 않습니다.
- AI 답변은 확인된 사실, 원인 후보, 다음 행동, 분석 한계로 나눠 보여 줍니다.

## 바로 써 보기

- 주소: `https://ctaleez51-art.github.io/sales-analysis/`
- 설치 없이 이 주소에서 바로 씁니다. 회원가입 후 로그인하고, [예시 데이터로 시작]을 누르면 됩니다.

## 사용 흐름

1. 로그인
2. 요금제 선택 (무료는 AI 분석 하루 5회, 프로는 토스페이먼츠로 결제)
3. 월별 매출 CSV 올리기 (여러 개 가능) 또는 예시 데이터
4. 지표가 자동으로 계산되어 대시보드에 나옴
5. 질문 → 분석 계획 확인 → 승인
6. AI 분석 답변 확인

## 환경변수 이름

| 이름 | 용도 | 위치 |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API 키 | Edge Function Secret |
| `TOSS_SECRET_KEY` | 토스페이먼츠 시크릿 키 (`test_sk_`) | Edge Function Secret |
| `url`, `key` | Supabase 주소, 공개용 publishable 키 | `part2/config.js` |
| `tossClientKey` | 토스페이먼츠 클라이언트 키 (`test_ck_`) | `part2/config.js` |

시크릿 키는 저장소와 브라우저 코드에 넣지 않습니다. `part2/config.js`에는 공개해도 되는 키만 넣습니다.

## 샘플 데이터

- `data/sales_2026_06.csv` ~ `sales_2026_09.csv`: 가상 건강보조식품 쇼핑몰의 6~9월 매출 (총 1,200행)
- `data/answer_key.json`: 정답표
- `part5/test-csv/coupang_orders_2026_09.csv`, `naver_orders_2026_09.csv`: 쿠팡, 네이버스토어 주문내역 원본 형식 시험 파일 (구매자·수취인 칸은 지움)
- CSV 형식은 `DevelopDoc/PRD.md` §7

## 구조

```
README.md
DevelopDoc/   PRD, TECH_SPEC, WORK_UNITS, FINAL_CHECKLIST
Submission/   STEP_CHECKLIST, SUBMISSION, ANALYSIS_SUBMISSION
part2/        로그인, 결제 화면
supabase/     DB 테이블, 권한, 결제 함수, 결제 승인 서버
data/         예시 CSV, 정답표
tools/        예시 데이터 생성 스크립트
part4/        지표 계산, AI 분석 서버
part5/        대시보드
```

## 제약

- 결제는 토스페이먼츠 테스트 모드입니다. 실제 돈이 나가지 않습니다.
- 시연용이라 이메일 인증 없이 바로 가입할 수 있습니다.
- CSV는 `date`, `product`, `channel` 열과, 매출·방문·광고비 같은 숫자 열이 하나 이상 있어야 합니다 (자세한 형식은 `DevelopDoc/PRD.md` §7).

## 역할분담

| 번호 | 역할 | 담당 | 브랜치 |
|---|---|---|---|
| 1 | 프로젝트매니저 (역할·일정, 문서 작성, 저장소 관리, 통합 테스트, 배포) | 이지연 | `main` 관리 |
| 2 | 로그인 + 결제창 (DB, 토스페이먼츠) | 허규현 | `feature/login-payment` |
| 3 | CSV 입력단 (더미 데이터, 정답 시나리오) | 김보겸 | `feature/csv-input` |
| 4 | 결과 출력단 (지표 계산식, 결과분석, OpenAI 연결) | 김성순 | `feature/part4-result-engine` |
| 5 | 대시보드 + CSS | 이두규 | `feature/dashboard` |
