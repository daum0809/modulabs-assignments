# 📨 GrowNote 발송 승인실 (HITL)

AI가 쓴 학부모 피드백 문자를 **내보내기 직전에 멈추고**, 승인 기준에 걸린 문자만 원장이 승인·수정·반려합니다. 기준에 걸리지 않은 문자는 자동으로 발송합니다.

- 그래프: LangGraph `interrupt()` + `Command(resume=...)` + SQLite 체크포인트
- 승인 기준 4개: 다른 학생 이름, 강의실·교재 쪽수, 근거 없는 비교, 민감 주제·결석 (모두 코드로 계산)
- 웹 데모: Streamlit / API 키 불필요 / 학생 데이터는 모두 가상

자세한 내용은 **[REPORT.md](REPORT.md)**에 있습니다. 구조도, 승인 기준과 막으려는 위험, 실행 결과를 담았습니다.

## 실행

```bash
cd grownote-hitl
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

streamlit run app.py            # 웹 데모
python run_demo.py              # REPORT의 실행 결과 재현 → results/demo_result.md
python -m unittest discover -s tests   # 테스트 10개
```

## 화면 사용법

1. **① 일괄 실행**: [피드백 문자 만들기]를 누르면 14명 중 8건은 자동 발송되고 6건은 대기로 갑니다.
2. **② 승인 대기함**: 걸린 부분이 빨간색으로 표시됩니다. [그대로 승인] / [수정 후 승인] / [반려] 중 하나를 고릅니다. 수정한 문장은 다시 검사합니다.
3. **③ 발송함·기록**: 처리 결과와 원장 결정 기록을 봅니다.

## 파일

| 파일 | 내용 |
|---|---|
| `app.py` | Streamlit 웹 데모 |
| `graph.py` | LangGraph 파이프라인, 발송함, 일괄 실행·재개 |
| `rules.py` | 승인 기준 R1~R4 |
| `compose.py` | 문자 초안 템플릿 |
| `data/students.json` | 가상 학생 14명 (위험 사례 6건 포함) |
| `run_demo.py` | 대본대로 결정을 넣어 실행 결과 생성 |
| `tests/test_all.py` | 규칙·그래프·웹 화면 테스트 |
