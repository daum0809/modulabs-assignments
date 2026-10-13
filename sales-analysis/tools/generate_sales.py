"""
가상 쇼핑몰(코스트코 건강보조식품 판매) 주간 매출 데이터 생성기.

정답 시나리오
- 6~8월: 3채널 합계 월 총매출 약 4,000만 원
- 9월: 쿠팡에서 경쟁 셀러가 주력 제품을 더 싸게 등록 -> 쿠팡 구매전환율 급락.
  광고비는 늘려 방문은 유지했지만 구매가 줄어 월 총매출 약 2,700만 원.
- 노이즈 변수: 공휴일(추석 등), 일부 품절, 네이버/자사몰 프로모션 (하락 원인 아님)
"""
import csv, random, calendar, sys
from datetime import date
from pathlib import Path

# 기본 저장 위치: 이 스크립트 옆의 ../data 폴더
OUT = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent.parent / "data")
random.seed(20260929)

# (제품명, 세부분류, 기준 판매가(원), 인기 가중치)
PRODUCTS = [
    ("커클랜드 시그니처 데일리 멀티비타민 500정", "종합비타민", 32990, 1.6),
    ("센트룸 실버 멀티비타민 275정", "종합비타민", 39990, 1.1),
    ("센트룸 우먼 멀티비타민 200정", "종합비타민", 36990, 0.8),
    ("커클랜드 시그니처 비타민D3 2000IU 600정", "비타민D", 19990, 1.4),
    ("커클랜드 시그니처 비타민C 1000mg 500정", "비타민C", 24990, 1.2),
    ("고려은단 비타민C 1000 300정", "비타민C", 29990, 1.0),
    ("커클랜드 시그니처 슈퍼 비타민B 콤플렉스 500정", "비타민B", 22990, 0.9),
    ("커클랜드 시그니처 비타민E 400IU 500정", "비타민E", 27990, 0.5),
    ("커클랜드 시그니처 오메가3 피쉬오일 1000mg 400캡슐", "오메가3", 29990, 1.5),
    ("종근당건강 프로메가 알티지 오메가3 듀얼 60캡슐", "오메가3", 45990, 0.9),
    ("커클랜드 시그니처 크릴오일 500mg 160캡슐", "오메가3", 44990, 0.6),
    ("종근당건강 락토핏 생유산균 골드 180포", "유산균", 39990, 1.3),
    ("커클랜드 시그니처 프로바이오틱스 90캡슐", "유산균", 39990, 0.8),
    ("커클랜드 시그니처 글루코사민 1500mg 375정", "관절건강", 34990, 0.9),
    ("커클랜드 시그니처 칼슘 마그네슘 아연 500정", "미네랄", 21990, 0.8),
    ("종근당건강 아이클리어 루테인지아잔틴 180캡슐", "눈건강", 42990, 0.9),
    ("정관장 홍삼정 에브리타임 10ml×30포", "홍삼", 89990, 0.7),
    ("뉴트리원 밀크씨슬 간건강 90정", "간건강", 25990, 0.5),
    ("커클랜드 시그니처 코엔자임Q10 300mg 100캡슐", "코엔자임Q10", 39990, 0.6),
    ("네이처스바운티 비오틴 10000mcg 120정", "비오틴", 24990, 0.4),
]
# 9월 쿠팡에서 경쟁 셀러 최저가가 붙는 주력 제품 (인기 상위 8개)
HIT = {p[0] for p in sorted(PRODUCTS, key=lambda p: -p[3])[:8]}

# 채널: 매출 비중, 가격 계수, 구매전환율, 장바구니율, 광고유입 비중, CTR, CPC(원)
CHANNELS = {
    "쿠팡":        dict(share=0.58, price=0.98, cvr=0.052, cart=0.11, paid=0.55, ctr=0.021, cpc=380),
    "네이버스토어": dict(share=0.27, price=1.00, cvr=0.041, cart=0.09, paid=0.50, ctr=0.018, cpc=400),
    "자사몰":      dict(share=0.15, price=1.03, cvr=0.033, cart=0.08, paid=0.65, ctr=0.015, cpc=450),
}

HOLIDAYS = {date(2026, 6, 3), date(2026, 6, 6), date(2026, 8, 15), date(2026, 8, 17),
            date(2026, 9, 24), date(2026, 9, 25), date(2026, 9, 26)}

# 월 총매출 목표(원) - 6~8월은 4천만 원 언저리, 9월은 채널 효과로 자연스럽게 떨어지게 둔다
MONTH_BASE = {6: 41_400_000, 7: 42_300_000, 8: 41_900_000, 9: 41_600_000}

# 품절(노이즈): (월, 구간번호, 채널, 제품 키워드) -> 품절 일수
STOCKOUT = {(6, 3, "자사몰", "크릴오일"): 3, (7, 4, "네이버스토어", "홍삼정"): 2,
            (8, 2, "쿠팡", "코엔자임"): 2, (9, 2, "자사몰", "비오틴"): 2}
# 프로모션(노이즈): (월, 구간번호, 채널) -> 할인율
PROMO = {(7, 2, "네이버스토어"): 0.10, (8, 3, "자사몰"): 0.05, (6, 4, "쿠팡"): 0.05}


def periods(month):
    last = calendar.monthrange(2026, month)[1]
    starts = [1, 8, 15, 22, 29]
    for i, s in enumerate(starts, 1):
        e = min(s + 6, last)
        yield i, date(2026, month, s), date(2026, month, e)


def jitter(x, pct):
    return x * random.uniform(1 - pct, 1 + pct)


def sept_coupang(prod, pno):
    """9월 쿠팡: (구매전환율 계수, 방문 계수, CPC 계수, 경쟁가 비율)"""
    if prod in HIT:
        cvr = {1: 0.45, 2: 0.27, 3: 0.21, 4: 0.19, 5: 0.19}[pno]
        return cvr, 1.06, 1.22, random.uniform(0.87, 0.91)
    return 0.80, 1.03, 1.15, random.uniform(1.00, 1.04)


total_w = sum(p[3] for p in PRODUCTS)
for month in (6, 7, 8, 9):
    rows = []
    mdays = calendar.monthrange(2026, month)[1]
    for pno, s, e in periods(month):
        days = (e - s).days + 1
        hol = sum(1 for d in HOLIDAYS if s <= d <= e)
        for ch, c in CHANNELS.items():
            for name, cat, base_price, w in PRODUCTS:
                disc = PROMO.get((month, pno, ch), 0.0) if w >= 0.8 else 0.0
                price = round(base_price * c["price"] / 10) * 10
                stock = next((v for (m, pn, cc, kw), v in STOCKOUT.items()
                              if m == month and pn == pno and cc == ch and kw in name), 0)

                # 기준 방문수: 목표 매출 -> 필요한 구매 -> 필요한 방문으로 역산
                target_rev = MONTH_BASE[month] * c["share"] * (w / total_w) * days / mdays
                qty = random.uniform(1.08, 1.25)
                purchases0 = target_rev / (price * qty)
                visits = jitter(purchases0 / c["cvr"], 0.08)
                cvr = c["cvr"] * random.uniform(0.9, 1.1)
                cpc = c["cpc"]
                comp = price * random.uniform(1.00, 1.05)

                if disc:
                    cvr *= 1 + disc * 2.2          # 할인하면 전환율 상승
                if hol:
                    visits *= 1 - 0.05 * hol / days * 7 * 0.5
                if month == 9:
                    if ch == "쿠팡":
                        fc, fv, fcpc, comp_ratio = sept_coupang(name, pno)
                        cvr *= fc
                        visits *= fv
                        cpc *= fcpc
                        comp = price * comp_ratio
                    else:
                        cvr *= random.uniform(0.95, 1.01)
                    if pno == 4:                    # 추석 연휴 택배 휴무
                        cvr *= 0.88
                if stock:
                    visits *= 1 - stock / days * 0.6
                    cvr *= 1 - stock / days * 0.7

                visits = max(1, round(visits))
                purchases = max(0, round(visits * cvr))
                cart_rate = c["cart"] * random.uniform(0.92, 1.08) * (cvr / c["cvr"]) ** 0.6
                add_to_cart = max(purchases, round(visits * cart_rate))
                units = round(purchases * qty)
                revenue = round(units * price * (1 - disc))
                clicks = round(visits * c["paid"] * random.uniform(0.93, 1.07)
                               * (1.22 if month == 9 and ch == "쿠팡" else 1))
                clicks = min(clicks, visits)
                impressions = round(clicks / (c["ctr"] * random.uniform(0.9, 1.1)))
                ad_spend = round(clicks * cpc * random.uniform(0.95, 1.05) / 10) * 10
                refund_rate = random.uniform(0.015, 0.04)
                refund = round(revenue * refund_rate / 10) * 10

                rows.append(dict(
                    date=s.isoformat(), period_end=e.isoformat(), days=days,
                    channel=ch, category=cat, product=name,
                    unit_price=price, discount_rate=disc,
                    competitor_min_price=round(comp / 10) * 10,
                    impressions=impressions, clicks=clicks, visits=visits,
                    add_to_cart=add_to_cart, purchases=purchases, units=units,
                    revenue=revenue, ad_spend=ad_spend, refund=refund,
                    holidays=hol, stockout_days=stock,
                ))
    path = f"{OUT}/sales_2026_{month:02d}.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    print(path, len(rows))
