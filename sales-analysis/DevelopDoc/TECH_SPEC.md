# 기술 명세서 - 매출분석 툴

| 항목 | 내용 |
|---|---|
| 선행 문서 | `DevelopDoc/PRD.md` |

---

## 1. 기술 스택
| 구분 | 선택 | 담당 |
|---|---|---|
| 프론트엔드 | HTML + JavaScript | 2번(로그인 화면), 5번(대시보드) |
| 백엔드 | Supabase Edge Function | 4번(AI 분석), 2번(결제 승인) |
| DB | Supabase (PostgreSQL, 로그인, 권한 RLS) | 2번 |
| 결제 | 토스페이먼츠 | 2번 |
| AI | OpenAI API | 4번 |
| 배포 | GitHub Pages | 1번 |

## 2. 구조
```
[로그인·결제] 2번
   ▼
[CSV 입력단] 3번
   ▼
[지표 계산 → 결과 분석(OpenAI)] 4번
   ▼
[대시보드] 5번
```

## 3. 모듈 사이 약속

### 3.1 CSV 입력단 → 지표 계산
- 넘겨주는 데이터 형식: 행 객체 배열 `rows`. 키는 CSV 열 이름입니다. 여러 달의 파일을 합친 배열입니다.
- 필수 키 3개: `date`, `product`, `channel`. 숫자 키(`unit_price`, `competitor_min_price`, `impressions`, `clicks`, `visits`, `add_to_cart`, `purchases`, `units`, `revenue`, `ad_spend`, `refund`)는 하나 이상 (자세한 것은 PRD §7)
- 없는 숫자 키로 만든 지표는 대시보드(`part5/app.js`)가 `null`(계산 불가)로 바꿉니다.
- 쿠팡, 네이버스토어 주문내역 원본은 `part5/csv.js`가 `date`, `product`, `channel`(쿠팡 또는 네이버스토어), `units`, `revenue`, `purchases`(주문 1건 = 1) 키로 바꿔 넘깁니다.
- 월은 `date`의 앞 7글자(`2026-09`)로 나눕니다.

### 3.2 지표 계산 → 대시보드
- 계산 결과 형식: `buildResult(rows)`가 돌려주는 객체

| 키 | 내용 |
|---|---|
| `currentPeriod`, `previousPeriod` | 이번 달, 바로 전 달 (예: `2026-09`, `2026-08`) |
| `current`, `previous` | 두 달의 지표 |
| `changes` | 전월 대비 증감률 (이미 % 단위) |
| `monthly_kpis` | 달마다 지표 |
| `channel_kpis` | 판매 채널별, 달마다 지표 |
| `diagnostics` | 쿠팡 경쟁가 진단 (경쟁 최저가가 우리 판매가보다 낮은 제품 목록) |

- 비율(CTR, CVR 등)은 소수로 오고, 화면에서 %로 바꿔 보여 줍니다. ROAS는 배로 보여 줍니다.
- `null`은 0이 아니라 "계산 불가"입니다.
- 대시보드는 숫자를 다시 계산하지 않습니다.

### 3.3 지표 계산식
입력단(3번)과 결과 출력단(4번)이 같은 계산식을 씁니다.

| 지표 | 계산식 |
|---|---|
| 합계 | `ad_spend`, `impressions`, `clicks`, `visits`, `add_to_cart`, `purchases`, `units`, `revenue`, `refund`를 먼저 더함 |
| `ctr` | clicks / impressions |
| `cvr` | purchases / visits |
| `cart_rate` | add_to_cart / visits |
| `cart_to_purchase_rate` | purchases / add_to_cart |
| `roas` | revenue / ad_spend |
| `cpc` | ad_spend / clicks |
| `cpa` | ad_spend / purchases |
| `aov` | revenue / purchases |
| `revenue_per_visit` | revenue / visits |
| 전월 대비 증감률 | (current − previous) / previous × 100 |

- 분모가 0이면 `null`입니다.
- `revenue`는 반품 전 매출입니다. `refund`를 빼지 않습니다.

## 4. 데이터 모델
| 테이블 | 내용 |
|---|---|
| `plans` | 요금제와 하루 AI 분석 한도 (무료 하루 5회) |
| `profiles` | 사용자별 요금제, 오늘 사용 횟수 |
| `payments` | 결제 기록 |

- 모든 테이블은 로그인한 본인 것만 보고 고칠 수 있습니다(RLS).

## 5. API
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/functions/v1/analyze-shop` | 계산 결과와 질문을 받아 AI 분석 글을 돌려줌. 로그인 토큰이 없으면 401, 하루 한도를 넘으면 429 (4번) |
| POST | Supabase 로그인 (`signUp`, `signInWithPassword`, `signOut`) | 회원가입, 로그인, 로그아웃 (2번) |
| POST | `/rest/v1/rpc/consume_analysis_quota` | 하루 사용 한도 1회 차감 (2번) |
| POST | `/functions/v1/confirm-payment` | 토스 결제 승인. 로그인, 주문 주인, 금액, 중복 결제, 이미 같은 요금제인지 확인한 뒤 승인하고 요금제를 프로로 바꿈 (2번) |

## 6. 폴더 구조
```
README.md
DevelopDoc/   PRD, TECH_SPEC, WORK_UNITS, FINAL_CHECKLIST (1번)
Submission/   STEP_CHECKLIST, SUBMISSION, ANALYSIS_SUBMISSION (1번)
part2/        로그인, 결제 화면 (2번)
supabase/     DB 테이블, 권한, 결제 함수, 결제 승인 서버 (2번)
data/         예시 CSV 4개, 정답표 (3번)
tools/        예시 데이터 생성 스크립트 (3번)
part4/        지표 계산, AI 서버 (4번)
part5/        대시보드 (5번)
```

## 7. 환경변수
비밀 키는 서버(Supabase Edge Function Secret)에만 두고 GitHub에 올리지 않습니다.

| 이름 | 용도 | 위치 |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API 키 | Edge Function Secret |
| `TOSS_SECRET_KEY` | 토스페이먼츠 시크릿 키 (`test_sk_`), 결제 승인용 | Edge Function Secret |
| Supabase secret 키 | 결제 승인 후 요금제 변경 (서버 전용 관리자 권한) | Edge Function Secret |
| `tossClientKey` | 토스페이먼츠 클라이언트 키 (`test_ck_`), 결제창 호출용 | `part2/config.js` (공개 가능) |
| Supabase URL, publishable 키 | DB 접속 정보 | `part2/config.js` (브라우저 공개용 키) |

## 8. 테스트
| 무엇 | 방법 | 결과 |
|---|---|---|
| 지표 계산 | 예시 CSV 4개(1,200행)로 계산해서 정답표 `data/answer_key.json`과 비교 | 전부 일치 (4번) |
| DB 권한 | A, B 두 계정으로 서로의 데이터 접근 (`supabase/rls_test.sql`) | 시험 10개 모두 통과 (2번) |
| 로그인 | 회원가입, 틀린 비밀번호, 새로고침 후 유지, 하루 한도, 로그아웃 | 통과 (2번) |
| CSV 오류 | 빈 파일, 필수 열 누락, 숫자 아닌 값, 날짜 형식 오류 | 오류 안내 나옴 (5번) |
| 합친 뒤 | 10/1 main에 합친 뒤 예시 CSV 4개로 다시 계산 | 합치기 전과 같음 (9월 매출 27,356,180원, -31.45%) (1번) |
