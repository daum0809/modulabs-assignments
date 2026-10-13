# TECH_SPEC — ShopInsight AI

## Architecture
Client → CSV Parser/Validator → Metric Engine → Analysis Planner → Visualization Renderer → Insight Generator

## Proposed Stack
- Next.js + TypeScript
- Tailwind CSS
- Recharts
- Server-side LLM API
- Supabase: Step 2 이후 저장이 필요할 때 연결
- Vercel
- GitHub

## Data Contract
필수 논리 필드:
- date
- product
- channel
- ad_spend
- visits
- purchases
- revenue

선택:
- impressions
- clicks
- add_to_cart
- category
- new_customers
- repeat_customers

## Metric Engine
- ROAS = revenue / ad_spend
- Purchase CVR = purchases / visits
- Cart rate = add_to_cart / visits
- Cart-to-purchase = purchases / add_to_cart
0으로 나누는 경우 null 처리하며 UI에서 계산 불가로 표시한다.

## AI Boundary
LLM은 원본 숫자의 산술 계산을 담당하지 않는다. Metric Engine의 구조화 결과를 입력받아 분석 계획, 해석, 시각화 사양, 후속 분석을 생성한다.

## Security
API 키는 서버 환경변수에만 저장한다. 저장소와 클라이언트 번들에 키를 포함하지 않는다. 해커톤은 가상 데이터만 사용한다.

## Structured Output
AI 결과는 최소 다음 구조를 따른다:
- summary
- evidence[]
- chart_spec
- next_questions[]
- limitations[]
