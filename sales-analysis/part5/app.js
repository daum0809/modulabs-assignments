/**
 * [5번] 대시보드 — 3번 CSV → 4번 buildResult → 화면 → (승인하면) 4번 AI 서버
 *
 * 화면은 숫자를 다시 계산하지 않는다. 모든 숫자는 buildResult 결과에서 오고,
 * 비율 변화가 더 필요하면 4번 엔진의 percentChange 를 그대로 쓴다.
 * 표시 규칙(4번 TEAM_HANDOFF): 비율은 소수 → %, roas 는 배, changes 는 이미 %, null 은 "계산 불가".
 */
import { buildResult, percentChange } from "../part4/result-engine.js";
import { readFiles, readTable } from "./csv.js";

// 4번 Supabase Edge Function (팀 Supabase 프로젝트, part4/RUN.md) — 주소는 공개돼도 되는 값, OpenAI 키는 서버 Secret 에만 있다.
// 서버는 verify_jwt=true 라서 로그인한 사용자의 access token 을 Authorization 헤더로 보내야 한다.
const AI_URL = "https://joxyzphsqjwuyobkboqe.supabase.co/functions/v1/analyze-shop";

// 로그인 토큰 — 4번 RUN.md 의 약속(getAccessToken · supabaseClient)과 2번 window.Auth.client 를 차례로 찾는다
// 2번 계정 상자는 consumeQuota·refreshAccount 때만 다시 그린다. 한도는 4번 서버가 세므로 화면이 알려 줘야 한다.
function refreshAccount() {
  try { window.Auth?.refreshAccount?.()?.catch?.((e) => console.warn("[dashboard] 계정 표시 갱신 실패", e)); }
  catch (e) { console.warn("[dashboard] 계정 표시 갱신 실패", e); }
}

async function accessToken() {
  if (typeof window.getAccessToken === "function") return (await window.getAccessToken()) || null;
  const client = window.Auth?.client || window.supabaseClient;
  if (!client?.auth?.getSession) return null;
  const { data } = await client.auth.getSession();
  return data?.session?.access_token || null;
}
const SAMPLE_FILES = ["sales_2026_06.csv", "sales_2026_07.csv", "sales_2026_08.csv", "sales_2026_09.csv"];
const SAMPLE_DIR = "../data/";

const $ = (id) => document.getElementById(id);
const statusEl = $("status");
const errorsEl = $("errors");
const appEl = $("app");

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const won = (n) => (n == null ? "계산 불가" : Math.round(n).toLocaleString("ko-KR") + "원");
// 막대 옆 짧은 표기: 만 원 단위, 천 단위 쉼표, 소수 없음(3,985만원). 1만 원 미만은 원 단위 그대로
const wonShort = (n) => (n == null ? "계산 불가" : Math.abs(n) < 10000 ? won(n) : Math.round(n / 10000).toLocaleString("ko-KR") + "만원");
const times = (n) => (n == null ? "계산 불가" : n.toFixed(2) + "배");
const rate = (n) => (n == null ? "계산 불가" : (n * 100).toFixed(2) + "%");
const count = (n) => (n == null ? "계산 불가" : Math.round(n).toLocaleString("ko-KR"));
const signed = (v) => (v == null ? "전월 비교 불가" : (v > 0 ? "+" : "") + v.toFixed(2) + "%");

// 오르면 나쁜 지표(비용)는 색을 반대로
const COST = new Set(["ad_spend", "cpa"]);
const tone = (key, v) => (v == null || v === 0 ? "" : (v > 0) !== COST.has(key) ? "positive" : "negative");

const KPIS = [
  { key: "revenue", label: "매출", fmt: won },
  { key: "ad_spend", label: "광고비", fmt: won },
  { key: "roas", label: "ROAS", fmt: times },
  { key: "cvr", label: "구매전환율", fmt: rate },
  { key: "cpa", label: "CPA (구매당 광고비)", fmt: won },
  { key: "aov", label: "객단가", fmt: won },
];

// 엔진이 없는 열을 0으로 더하는 것(R1 빈칸≠0 위반)을 막는 안전장치. csv.js 는 식별 3열만 필수라(10/1)
// 판매 지표만 올린 CSV 처럼 숫자 열이 빠지면 여기서 그 열로 만든 값만 null(계산 불가)로 바꾼다. 숫자를 새로 계산하지는 않는다.
const OPTIONAL = {
  revenue: ["revenue", "roas", "aov", "revenue_per_visit"],
  ad_spend: ["ad_spend", "roas", "cpc", "cpa"],
  visits: ["visits", "cvr", "cart_rate", "revenue_per_visit"],
  purchases: ["purchases", "cvr", "cpa", "aov", "cart_to_purchase_rate"],
  add_to_cart: ["add_to_cart", "cart_rate", "cart_to_purchase_rate"],
  impressions: ["impressions", "ctr"],
  clicks: ["clicks", "ctr", "cpc"],
  units: ["units"],
  refund: ["refund"],
};
const DIAG_COLS = ["unit_price", "competitor_min_price"]; // 쿠팡 경쟁가 진단(4번 diagnostics)
const COL_LABEL = { revenue: "매출", ad_spend: "광고비", visits: "방문", purchases: "구매", add_to_cart: "장바구니", impressions: "광고 노출", clicks: "광고 클릭", units: "판매 수량", refund: "반품액", unit_price: "우리 판매가", competitor_min_price: "경쟁 최저가" };
const filled = (v) => v != null && String(v).trim() !== "";

// 4번 diagnostics.evidence_rule 은 코드 식("channel=쿠팡 AND competitor_min_price < unit_price") — 화면에는 문장으로 바꿔 보여 준다.
// 식이 바뀌어도 깨지지 않게, 모르는 식은 열 이름만 한국어로 바꾼다.
function ruleText(rule) {
  const r = String(rule || "").trim();
  if (!r) return "";
  if (/^channel\s*=\s*쿠팡\s+AND\s+competitor_min_price\s*<\s*unit_price$/i.test(r)) return "쿠팡에서 경쟁 최저가가 우리 판매가보다 낮은 제품";
  return r
    .replace(/\bchannel\s*=\s*/g, "판매 채널 ")
    .replace(/\b[a-z_]+\b/g, (w) => COL_LABEL[w] || w)
    .replace(/\s+AND\s+/g, " 이고 ")
    .replace(/\s*<\s*/g, " < ");
}

// 한 행이라도 비어 있으면 합계가 틀리므로 "없음"으로 본다. 돌려주는 값: { 열: 판단 근거 }
function columnGaps(rows) {
  const gaps = {};
  for (const c of [...Object.keys(OPTIONAL), ...DIAG_COLS]) {
    const absent = rows.filter((r) => !(c in r)).length;
    const blank = rows.filter((r) => c in r && !filled(r[c])).length;
    const name = `${COL_LABEL[c]}(${c})`;
    if (absent === rows.length) gaps[c] = `올린 CSV에 ${name} 열이 없음`;
    else if (absent) gaps[c] = `일부 파일에 ${name} 열이 없음 (${absent.toLocaleString("ko-KR")}행)`;
    else if (blank) gaps[c] = `${name} 칸이 ${blank.toLocaleString("ko-KR")}행 비어 있음`;
  }
  return gaps;
}

// null 인 값의 판단 근거 — 없는 열 때문인지, 나눌 값(분모)이 0이라서인지
const DENOM = { roas: ["ad_spend", "광고비가"], cvr: ["visits", "방문이"], cpa: ["purchases", "구매가"], aov: ["purchases", "구매가"], cart_rate: ["visits", "방문이"], cart_to_purchase_rate: ["add_to_cart", "장바구니가"] };
function whyNull(kpi, key, gaps) {
  const col = Object.keys(OPTIONAL).find((c) => OPTIONAL[c].includes(key) && gaps[c]);
  if (col) return gaps[col];
  const d = DENOM[key];
  if (d && kpi?.[d[0]] === 0) return `${d[1]} 0이라 나눌 수 없음`;
  return "";
}

function maskResult(result, gaps) {
  const missing = Object.keys(gaps);
  if (!missing.length) return result;
  const out = structuredClone(result);
  const fields = new Set(missing.flatMap((c) => OPTIONAL[c] || []));
  const blank = (k) => { if (k) for (const f of fields) if (f in k) k[f] = null; };
  blank(out.current);
  blank(out.previous);
  blank(out.changes); // 전월 대비도 — 없는 열끼리 비교한 값이 남지 않게
  Object.values(out.monthly_kpis || {}).forEach(blank);
  Object.values(out.channel_kpis || {}).forEach((byMonth) => Object.values(byMonth).forEach(blank));
  const diagMissing = DIAG_COLS.filter((c) => missing.includes(c));
  if (diagMissing.length && out.diagnostics) {
    out.diagnostics = { ...out.diagnostics, coupang_undercut_product_count: null, coupang_undercut_products: null,
      unavailable_reason: diagMissing.map((c) => gaps[c]).join(" · ") };
  }
  out.data_gaps = { missing_columns: missing, reasons: gaps, note: "이 열로 만든 값은 null(계산 불가)이며 0이 아니다. 이 값으로 결론을 내리지 말 것." };
  return out;
}

let state = null; // { rows, result, source, gaps }
let aiRequest = null; // 확인용으로 바꿔 끼울 수 있는 AI 요청 함수

function showErrors(list) {
  errorsEl.hidden = !list.length;
  errorsEl.innerHTML = list.length
    ? `<b>불러오지 못했습니다</b><ul>${list.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>`
    : "";
}

function bars(el, items) {
  const max = Math.max(...items.map((x) => x.value ?? 0), 1);
  el.innerHTML = items.map((x) => `
    <div class="barrow${x.cls ? ` ${x.cls}` : ""}"><b>${esc(x.label)}</b>
      <div class="track"><div class="bar" style="width:${Math.max(2, ((x.value ?? 0) / max) * 100)}%"></div></div>
      <span>${esc(x.text)}${x.sub ? `<small class="${x.subTone || ""}">${esc(x.sub)}</small>` : ""}${x.badge ? `<em class="bar-badge">${esc(x.badge)}</em>` : ""}</span>
    </div>`).join("");
}

// ── 매출 진단서: 결론 문장 · 분해 줄 · 채널 한 줄 ──
// 매출 = 방문 × 구매 전환율 × 객단가 (revenue = visits × purchases/visits × revenue/purchases).
// 네 칸 모두 4번 엔진 changes 값을 그대로 쓰고, 화면은 "어느 칸이 가장 크게 움직였나"만 고른다.
const STEADY = 3; // ±3% 안은 "유지"
const pct1 = (v) => (v > 0 ? "+" : "") + v.toFixed(1) + "%";
const monthName = (p) => (p && /^\d{4}-\d{2}$/.test(p) ? `${Number(p.slice(5))}월` : p || "");

const DECOMP = [
  { key: "revenue", label: "매출" },
  { key: "visits", label: "방문" },
  { key: "cvr", label: "구매 전환율" },
  { key: "aov", label: "객단가" },
];
// [맥락, 핵심] — 핵심만 굵게 보여 준다
const DOWN_LINE = {
  visits: () => ["들어오는 손님이", "줄었다."],
  cvr: (c) => (c.visits != null && Math.abs(c.visits) < STEADY ? ["손님은 그대로인데,", "사지 않았다."] : ["들어온 손님이", "덜 샀다."]),
  aov: () => ["한 번에 사는 금액이", "줄었다."],
};
const UP_LINE = {
  visits: () => ["들어오는 손님이", "늘었다."],
  cvr: () => ["들어온 손님이", "더 많이 샀다."],
  aov: () => ["한 번에 사는 금액이", "늘었다."],
};

// 받침이 있으면 "을", 없으면 "를" (구매 전환율을 · 객단가를)
const objParticle = (w) => { const c = w.charCodeAt(w.length - 1) - 0xac00; return c >= 0 && c < 11172 && c % 28 ? "을" : "를"; };

// 결론을 이끈 요소 — 매출이 줄면 가장 많이 줄어든 요소, 늘면 가장 많이 늘어난 요소 (±3% 안이면 없음)
function leadFactor(changes) {
  const down = changes.revenue < 0;
  const cand = ["visits", "cvr", "aov"].filter((k) => changes[k] != null);
  if (!cand.length) return null;
  const pick = cand.reduce((a, b) => ((down ? changes[b] < changes[a] : changes[b] > changes[a]) ? b : a));
  return Math.abs(changes[pick]) < STEADY || (down ? changes[pick] > 0 : changes[pick] < 0) ? null : pick;
}

function renderVerdict({ changes, current, currentPeriod, previousPeriod, channel_kpis, diagnostics }) {
  const m = monthName(currentPeriod);
  $("verdict-meta").textContent = `매출 진단 · ${previousPeriod ? `${previousPeriod} → ${currentPeriod}` : currentPeriod}`;
  const rev = previousPeriod ? changes.revenue ?? null : null;
  const lead = rev == null || rev === 0 ? null : leadFactor(changes);

  let line;
  // 세 단계 크기: 작은 맥락("9월 매출") → 가장 큰 결과("31.5% 감소") → 중간 원인(핵심 동사만 굵게)
  const label = `<span class="vl-label">${esc(m)} 매출</span>`;
  if (rev == null) line = `${label}<span class="vl-num">${esc(won(current.revenue))}</span><span class="verdict-sub">전월과 비교하려면 연속된 두 달 이상의 파일을 함께 올리세요.</span>`;
  else if (rev === 0) line = `${label}<span class="vl-num">전월과 같음</span>`;
  else {
    const num = `<span class="vl-num ${rev < 0 ? "v-neg" : "v-pos"}">${Math.abs(rev).toFixed(1)}% ${rev < 0 ? "감소" : "증가"}</span>`;
    // 방문 · 전환율 · 객단가 중 계산 불가(없는 열)가 있으면 "여러 요인" 이라고 단정하지 않는다
    const unknown = DECOMP.filter(({ key }) => key !== "revenue" && changes[key] == null).map(({ label }) => label);
    const [ctx, key] = lead ? (rev < 0 ? DOWN_LINE : UP_LINE)[lead](changes)
      : unknown.length ? [`${unknown.join(" · ")}${objParticle(unknown.at(-1))} 알 수 없어`, "원인은 나눠 볼 수 없다."]
      : ["여러 요인이", rev < 0 ? "조금씩 줄었다." : "조금씩 늘었다."];
    line = `${label}${num}<span class="vl-why">${esc(ctx)} <b class="verdict-mark">${esc(key)}</b></span>`;
  }
  $("verdict-line").innerHTML = line;

  $("decomp").innerHTML = DECOMP.map(({ key, label }, i) => {
    const v = previousPeriod ? changes[key] ?? null : null;
    const hit = key === lead;
    const note = v == null ? (previousPeriod ? "계산 불가" : "전월 비교 불가") : hit ? (rev < 0 ? "여기서 무너짐" : "여기서 늘었다") : key !== "revenue" && Math.abs(v) < STEADY ? "유지" : "";
    const cls = ["dc", key === "revenue" ? `dc-total ${v == null ? "" : v < 0 ? "dc-down" : "dc-up"}` : "", hit ? (rev < 0 ? "dc-hit" : "dc-lift") : "", v == null ? "dc-na" : ""].filter(Boolean).join(" ");
    const op = i === 0 ? "" : `<span class="op" aria-hidden="true">${i === 1 ? "=" : "×"}</span>`;
    return `${op}<div class="${cls}" role="listitem"><span>${esc(label)}</span><strong>${v == null ? "—" : esc(pct1(v))}</strong>${note ? `<small>${esc(note)}</small>` : ""}</div>`;
  }).join("");

  // 가장 크게 떨어진(오른) 판매 채널 — 채널 ROAS 변화는 채널 막대와 같은 percentChange
  const chEl = $("verdict-channel");
  const moves = previousPeriod ? Object.entries(channel_kpis).map(([ch, byMonth]) => {
    const now = byMonth[currentPeriod], before = byMonth[previousPeriod];
    return { ch, roas: now?.roas ?? null, v: before ? percentChange(now?.roas ?? null, before.roas) : null };
  }).filter((x) => x.v != null) : [];
  if (moves.length) {
    const worst = moves.reduce((a, b) => (b.v < a.v ? b : a));
    const under = Array.isArray(diagnostics?.coupang_undercut_products) ? diagnostics.coupang_undercut_products.length : null;
    const tail = worst.ch === "쿠팡" && under ? ` · 쿠팡에서 경쟁 최저가보다 비싼 상품 ${under}개` : "";
    chEl.innerHTML = worst.v < 0
      ? `가장 크게 떨어진 판매 채널 <b>${esc(worst.ch)}</b> ROAS ${esc(times(worst.roas))} (${esc(pct1(worst.v))})${esc(tail)}`
      : `모든 판매 채널의 ROAS가 전월보다 같거나 올랐습니다.`;
    chEl.hidden = false;
    state.worstChannel = worst.v < 0 ? worst.ch : null;
  } else { chEl.hidden = true; state.worstChannel = null; }
}

// 매출 칸 추세선 — monthly_kpis 의 월별 매출을 그대로 선으로 (값이 두 개 이상일 때만)
// 가로: 금액 눈금(옅은 점선) · 세로: 월별 기준선 · 점 위: 전월 대비 %(4번 엔진 percentChange 그대로, 연속된 달일 때만)
const nextMonth = (p) => { const [y, m] = p.split("-").map(Number); return m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, "0")}`; };
function niceStep(span) {
  const raw = span / 2.5, mag = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 2.5, 5, 10].map((k) => k * mag).find((st) => st >= raw) || 10 * mag;
}
function sparkline(monthly_kpis, down) {
  const pts = Object.entries(monthly_kpis).map(([p, k]) => [p, k.revenue]).filter(([, v]) => v != null);
  if (pts.length < 2) return "";
  const vals = pts.map(([, v]) => v), min = Math.min(...vals), max = Math.max(...vals), span0 = max - min || max || 1;
  const lo = min - span0 * 0.2, hi = max + span0 * 0.45; // 위쪽은 % 라벨 자리
  const W = 360, H = 118, L = 46, R = 18, T = 8, B = 20;
  const x = (i) => L + (i * (W - L - R)) / (pts.length - 1);
  const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const step = niceStep(max - min || max * 0.1 || 1);
  const ticks = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) if (t >= 0) ticks.push(t);
  const man = (v) => `${Math.round(v / 10000).toLocaleString("ko-KR")}만`;
  const last = pts.length - 1;
  const pctOf = (i) => (i > 0 && nextMonth(pts[i - 1][0]) === pts[i][0] ? percentChange(pts[i][1], pts[i - 1][1]) : null);
  const label = pts.map(([p, v], i) => { const c = pctOf(i); return `${p} ${wonShort(v)}${c == null ? "" : ` (전월 대비 ${pct1(c)})`}`; }).join(", ");
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" role="img" aria-label="월별 매출 추세: ${esc(label)}">
    ${ticks.map((t) => `<line class="spark-grid" x1="${L}" y1="${y(t).toFixed(1)}" x2="${W - R}" y2="${y(t).toFixed(1)}"/><text class="spark-tick" x="${L - 6}" y="${(y(t) + 3.5).toFixed(1)}" text-anchor="end">${esc(man(t))}</text>`).join("")}
    ${pts.map((_, i) => `<line class="spark-guide" x1="${x(i).toFixed(1)}" y1="${T}" x2="${x(i).toFixed(1)}" y2="${H - B}"/>`).join("")}
    <polyline points="${pts.map(([, v], i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
    ${pts.map(([, v], i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="${i === last ? 5 : 3}" class="${i === last ? (down ? "spark-down" : "spark-up") : "spark-dot"}"/>`).join("")}
    ${pts.map(([, v], i) => { const c = pctOf(i); if (c == null) return ""; const cls = i === last ? (c < 0 ? "spark-pct spark-pct-neg" : "spark-pct spark-pct-pos") : "spark-pct"; // 마지막 점은 선이 위에서 내려오므로 라벨을 점 왼쪽 같은 높이(선 아래 빈 곳)에 둔다
      const lx = i === last ? x(i) - 10 : x(i), ly = i === last ? y(v) + 4.5 : y(v) - 10;
      return `<text class="${cls}" x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="${i === last ? "end" : "middle"}">${esc(pct1(c))}</text>`; }).join("")}
    ${pts.map(([p], i) => `<text class="spark-month" x="${x(i).toFixed(1)}" y="${H - 4}" text-anchor="middle">${esc(monthName(p))}</text>`).join("")}
  </svg>`;
}

function render(rows, source) {
  const gaps = columnGaps(rows);
  const result = maskResult(buildResult(rows), gaps);
  state = { rows, result, source, gaps };
  window.dispatchEvent(new CustomEvent("dashboard:data"));
  const { current, previous, changes, currentPeriod, previousPeriod, monthly_kpis, channel_kpis, diagnostics } = result;
  if (!current) {
    showErrors(["날짜(date)로 묶을 수 있는 행이 없습니다."]);
    appEl.hidden = true;
    return;
  }

  // 맨 위 결론 문장 · 분해 줄 · 채널 한 줄
  renderVerdict(result);

  // KPI 6칸 — 매출은 맨 앞 큰 칸(추세선), 나머지 5칸은 작게
  $("kpis").innerHTML = KPIS.map(({ key, label, fmt }, i) => {
    const v = changes[key] ?? null;
    const why = current[key] == null ? whyNull(current, key, gaps) : "";
    const body = `<span>${esc(label)}</span><strong>${esc(fmt(current[key]))}</strong>
      ${why ? `<small class="why">근거: ${esc(why)}</small>` : ""}
      <small class="${tone(key, v)}">${esc(signed(v))}${v == null ? "" : " 전월 대비"}</small>`;
    return i === 0
      ? `<article class="kpi-lead"><div>${body}</div><div class="spark-wrap">${sparkline(monthly_kpis, (v ?? 0) < 0) || `<p class="spark-empty">두 달 이상 올리면 월별 매출 추세가 여기에 보입니다.</p>`}</div></article>`
      : `<article>${body}</article>`;
  }).join("");

  // 월별 매출 — 이번 달 막대만 강조
  bars($("months"), Object.entries(monthly_kpis).map(([p, k]) => ({ label: p, value: k.revenue, text: wonShort(k.revenue), cls: p === currentPeriod ? "is-current" : "" })));

  // 없는 열 안내 — 해당 칸은 "계산 불가"
  const gapsEl = $("gaps");
  const gapList = Object.values(gaps);
  gapsEl.hidden = !gapList.length;
  gapsEl.innerHTML = gapList.length
    ? `<b>일부 칸은 계산 불가로 표시합니다</b> — 0으로 계산하면 틀린 숫자가 되기 때문입니다. AI에도 계산 불가로 전달합니다.
       <ul>${gapList.map((g) => `<li>${esc(g)}</li>`).join("")}</ul>`
    : "";

  // 이번 달 퍼널 — 장바구니 열이 없으면 구매는 방문 대비(cvr)로 보여 준다
  const noCart = current.add_to_cart == null;
  const steps = [
    ["방문", current.visits, ""],
    ["장바구니", current.add_to_cart, noCart ? `근거: ${gaps.add_to_cart || "장바구니 값 없음"}` : current.cart_rate == null ? `근거: ${whyNull(current, "cart_rate", gaps)}` : `방문의 ${rate(current.cart_rate)}`],
    ["구매", current.purchases, noCart ? `방문의 ${rate(current.cvr)}` : current.cart_to_purchase_rate == null ? `근거: ${whyNull(current, "cart_to_purchase_rate", gaps)}` : `장바구니의 ${rate(current.cart_to_purchase_rate)}`],
  ];
  // 폭은 같게 둔다 — 폭을 줄이면 실제 낙폭과 상관없는 모양이 된다. 비율 글자로 낙폭을 보여 준다
  $("funnel").innerHTML = steps.map(([name, n, note]) =>
    `<div class="funnel-step"><b>${name}</b> <span class="fn-n">${esc(count(n))}</span>${note ? ` <small>${esc(note)}</small>` : ""}</div>`).join("");

  // 판매 채널별 (이번 달 ROAS, 전월 대비) — 채널마다 고유색(이름으로 고정), 가장 크게 떨어진 채널은 빨간 이름 + 표시
  const CH_COLOR = { 쿠팡: 1, 네이버스토어: 2, 자사몰: 3 };
  let extra = 3;
  bars($("channels"), Object.entries(channel_kpis).map(([ch, byMonth]) => {
    const now = byMonth[currentPeriod], before = previousPeriod ? byMonth[previousPeriod] : null;
    const v = before ? percentChange(now?.roas ?? null, before.roas) : null;
    const why = now?.roas == null ? whyNull(now, "roas", gaps) : "";
    return { label: ch, value: now?.roas, text: times(now?.roas ?? null), sub: why ? ` 근거: ${why}` : v == null ? "" : ` ${signed(v)}`, subTone: why ? "" : tone("roas", v),
      cls: `ch-${CH_COLOR[ch] || (extra++ % 5) + 1}${ch === state.worstChannel ? " is-worst" : ""}`, badge: ch === state.worstChannel ? "가장 크게 하락" : "" };
  }));

  // 경쟁가 진단 (4번 diagnostics)
  const diagEl = $("diagnostics");
  if (diagnostics && diagnostics.coupang_undercut_products === null) {
    diagEl.hidden = false;
    diagEl.querySelector(".diag-body").innerHTML =
      `<p><b>진단 불가</b> — 경쟁가가 더 낮은 제품이 없다는 뜻이 아닙니다.</p>
       <p class="diag-note">근거: ${esc(diagnostics.unavailable_reason || "경쟁가 열이 없음")}
       <span class="diag-rule">진단 기준: ${esc(ruleText(diagnostics.evidence_rule))} — 우리 판매가와 경쟁 최저가가 모든 행에 있어야 셀 수 있습니다.</span></p>`;
  } else if (diagnostics && Array.isArray(diagnostics.coupang_undercut_products)) {
    const list = diagnostics.coupang_undercut_products;
    diagEl.hidden = false;
    diagEl.querySelector(".diag-body").innerHTML = list.length
      ? `<p>${esc(currentPeriod)} 쿠팡에서 <b>경쟁 최저가가 우리 판매가보다 낮은 제품 ${list.length}개</b></p>
         <ul class="diag-list">${list.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>
         <p class="diag-note">${esc(diagnostics.causality_note || "")} <span class="diag-rule">기준: ${esc(ruleText(diagnostics.evidence_rule))}</span></p>`
      : `<p>${esc(currentPeriod)} 쿠팡에서 경쟁 최저가가 더 낮은 제품이 없습니다.</p>`;
  } else diagEl.hidden = true;

  // 결론 영역 맨 아래 한 줄 — 분해 줄에 없는 것(광고비)만 보탠다. changes 값을 그대로 옮긴다.
  // 4번 엔진은 바로 앞 달(연속된 달)이 있을 때만 previousPeriod 를 준다 — 6월 · 9월만 올리면 비교하지 않는다
  const months = Object.keys(monthly_kpis);
  const ad = changes.ad_spend, buy = changes.purchases;
  $("insight").textContent = previousPeriod
    ? ad == null || buy == null
      ? ""
      : ad > 0 && buy < 0
        ? `광고비는 ${pct1(ad)} 늘렸지만 구매는 ${pct1(buy)}.`
        : `광고비 ${pct1(ad)} · 구매 ${pct1(buy)}.`
    : months.length > 1
      ? `올린 달: ${months.join(", ")} — 바로 앞 달이 없어 비교하지 않았습니다.`
      : "";

  // 필요한 열이 없는 질문 버튼은 숨긴다 (data-needs). 열이 다 있는 파일을 올리면 다시 보인다
  document.querySelectorAll(".faq-btn[data-needs]").forEach((b) => {
    b.hidden = b.dataset.needs.split(" ").some((c) => gaps[c]);
  });

  $("answer").innerHTML = "";
  showErrors([]);
  appEl.hidden = false;
  statusEl.textContent = `${source} · ${rows.length.toLocaleString("ko-KR")}행 · ${previousPeriod ? `${previousPeriod} → ${currentPeriod}` : currentPeriod}`;
}

async function loadSample() {
  statusEl.textContent = "예시 데이터를 불러오는 중…";
  try {
    const texts = await Promise.all(SAMPLE_FILES.map(async (f) => {
      const res = await fetch(SAMPLE_DIR + f);
      if (!res.ok) throw new Error(`${f} 를 찾지 못했습니다 (${res.status})`);
      return [f, await res.text()];
    }));
    const parts = texts.map(([f, t]) => readTable(f, t));
    const errors = parts.flatMap((p) => p.errors);
    if (errors.length) throw new Error(errors.join(" / "));
    render(parts.flatMap((p) => p.rows), `예시 CSV ${SAMPLE_FILES.length}개`);
  } catch (e) {
    statusEl.textContent = "예시 데이터를 불러오지 못했습니다.";
    showErrors([e.message, "저장소 최상위 폴더를 웹 서버로 열고 /part5/ 로 들어왔는지 확인해 주세요."]);
  }
}

// 로그아웃하면 앞 사람의 데이터 · 분석이 화면에 남지 않게 처음 상태로 새로 불러온다(10/1).
// 2번 auth.js 는 로그아웃 때 로그인 창만 덮어서, 다시 로그인하면 이전 분석이 그대로 보였다 — 같은 브라우저를 다른 사람이 쓸 수 있다.
window.Auth?.client?.auth?.onAuthStateChange?.((event) => { if (event === "SIGNED_OUT") location.reload(); });

$("sample").addEventListener("click", loadSample);
$("file").addEventListener("change", async (e) => {
  const input = e.target;
  statusEl.textContent = "파일을 읽는 중…";
  const out = await readFiles(input.files);
  input.value = ""; // 같은 파일을 다시 골라도 change 가 나게
  if (out.errors.length) {
    state = null;
    appEl.hidden = true;
    statusEl.textContent = "파일을 확인해 주세요.";
    showErrors(out.errors);
    return;
  }
  render(out.rows, [`CSV ${out.files.length}개`, ...(out.notes || [])].join(" · ")); // 예: "CSV 1개 · 쿠팡 주문내역 원본 12건"
});

// 계획 카드(approval.js)가 쓰는 연결부
window.dashboard = {
  rows: () => state?.rows ?? null,
  result: () => state?.result ?? null,
  gaps: () => state?.gaps ?? {},
  // 승인했을 때만 불린다. 돌려주는 값: { ok, kind }
  analyze(question) {
    if (!state) return Promise.resolve({ ok: false, kind: "no-data" });
    const body = { result: state.result, question };
    const fail = (kind) => Object.assign(new Error(kind), { kind });
    // 하루 한도는 4번 AI 서버가 센다(consume_analysis_quota, 넘으면 429). 화면에서 또 세면 한 번에 2회가 줄어든다.
    // 화면은 로그인 토큰만 확인한다. [다시 시도]도 매번 토큰부터 다시 찾는다.
    const request = async (signal) => {
      let token;
      try { token = await accessToken(); }
      catch (e) { console.warn("[dashboard] 로그인 확인 실패", e); throw fail("login"); }
      if (!token) throw fail("login"); // 토큰 없이 부르면 서버가 401
      const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
      const res = await (aiRequest
        ? aiRequest(body, signal, headers)
        : fetch(AI_URL, { method: "POST", headers, body: JSON.stringify(body), signal }));
      refreshAccount(); // 응답이 왔으면 서버가 한도를 셌다 — 2번 계정 상자의 "오늘 N회"를 다시 그린다
      return res;
    };
    return window.runAnalysis(request, { target: $("answer") });
  },
  // 확인용: 실제 서버 대신 가짜 응답을 넣는다 — fn(body, signal, headers). null 이면 실제 서버
  setAIRequest(fn) { aiRequest = typeof fn === "function" ? fn : null; },
};
