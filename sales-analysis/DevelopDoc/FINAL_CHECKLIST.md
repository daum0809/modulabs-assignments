# 최종 체크리스트 - 매출분석 툴

> 제출 전(10/02 오전 10시 마감)에 전 항목을 확인합니다.

| 항목 | 내용 |
|---|---|
| 관련 문서 | `DevelopDoc/PRD.md`, `DevelopDoc/TECH_SPEC.md`, `DevelopDoc/WORK_UNITS.md` |

---

## Part A · 기능
근거: `Submission/SUBMISSION.md` ⑤ 테스트 결과표
- [x] 로그인
- [x] 결제
- [x] CSV 업로드
- [x] 지표 계산
- [x] AI 분석
- [x] 대시보드

## Part B · 보안
- [x] 비밀 키(`OPENAI_API_KEY`, `TOSS_SECRET_KEY`, Supabase secret 키)가 저장소에 없고 Edge Function Secret에만 있음
- [x] `part2/config.js`에 공개 키(publishable, `test_ck_`)만 있음 (10/1 확인)

## Part C · 제출물
- [x] GitHub 링크 (https://github.com/ctaleez51-art/sales-analysis)
- [x] 저장소 맨 위에 `README.md` (서비스 소개)
- [x] `DevelopDoc/`에 PRD.md, TECH_SPEC.md, WORK_UNITS.md, FINAL_CHECKLIST.md
- [x] 시연하거나 체험할 수 있는 URL 또는 프로그램 (https://ctaleez51-art.github.io/sales-analysis/)
- [x] 발표 자료 (역할 분담, 개발 일정 포함)

---

## 확인
| 항목 | 내용 |
|---|---|
| 확인한 사람 | 1번 이지연 |
| 확인한 날 | 2026-10-01 |
