/**
 * [5번] CSV 읽기 · 검증 — 3번 명세(docs/part3_to_part4_metric_spec.md "CSV 읽기")를 따른다.
 *   - 여러 파일을 한 번에 받아 행을 합친다 (파일끼리 열 구성이 달라도 필수 열만 있으면 됨)
 *   - 숫자 열은 있는 것만 검사한다. 없는 열로 만든 지표는 app.js 가 "계산 불가"로 바꾼다(0으로 두지 않음)
 *   - UTF-8 BOM 제거, 줄바꿈 \n · \r\n, 따옴표 안 쉼표 · 줄바꿈 · "" 처리
 *   - 실패하면 이유를 모아서 돌려준다 (파일명 · 행 번호 · 열 이름)
 * 숫자는 여기서 바꾸지 않는다. 계산은 4번 buildResult 가 한다.
 */
// 필수 = 행을 나누는 식별 3열(날짜 · 상품 · 판매 채널). 판매 지표만 있는 CSV 도 분석할 수 있게 숫자 열은 고를 수 있다(10/1).
// 4번 buildResult 는 없는 열을 0으로 더하므로, 없는 열로 만든 지표는 app.js 의 columnGaps · maskResult 가 null(계산 불가)로 바꾼다.
// 14열이 모두 있으면 예전과 같다 — 3번 정답표(answer_key.json) 검증 그대로.
export const REQUIRED = ["date", "product", "channel"];
export const NUMBER_COLUMNS = ["unit_price", "competitor_min_price", "impressions", "clicks", "visits", "add_to_cart",
  "purchases", "units", "revenue", "ad_spend", "refund"];
const MAX_ERRORS = 5;
// 마켓(네이버스토어 · 쿠팡)에서 내려받은 주문내역 원본은 제목 줄이 한국어이고 주문 한 건씩이라 바로 읽을 수 없다(10/1).
// 영어 열 이름 목록만 보여 주면 무엇을 고칠지 모르므로, 파일별로는 짧은 이유를, 바꾸는 방법은 readFiles 가 한 번만 붙인다.
const RAW_EXPORT_GUIDE = "바꾸는 방법: 날짜 · 상품 · 판매 채널별로 합친 CSV 로 만들어 제목 줄을 date · product · channel 과 숫자 열(예: revenue · purchases · units)로 바꿔 올려 주세요. 예시: part5/test-csv/sales_only_2026_09.csv";
const looksRawExport = (head) => head.some((h) => /[가-힣]/.test(h));

// 알아보는 마켓 원본 형식 — 제목 줄에 need 가 모두 있으면 주문 한 건을 우리 열 한 행으로 바꾼다(10/1, 규현님 쿠팡 샘플로 확인).
// 엔진이 행을 더해 월별 · 채널별 값을 내므로 날짜 × 상품별로 따로 합치지 않아도 결과가 같다.
// 원본에 없는 광고비 · 방문 등은 열을 만들지 않는다(0 이 아니라 app.js 가 "계산 불가"로 표시).
// exclude: [열, 조건] — 하나라도 맞으면 매출에서 뺀다(취소 · 반품).
const MARKET_FORMATS = [{
  label: "쿠팡 주문내역 원본", channel: "쿠팡",
  need: ["주문번호", "주문일", "등록상품명", "구매수(수량)", "결제액"],
  cols: { date: "주문일", product: "등록상품명", units: "구매수(수량)", revenue: "결제액" },
  exclude: [["주문상태", /취소|반품/]],
}, {
  // 10/1 규현님 네이버스토어 샘플로 확인. 금액은 할인 뒤 · 배송비 제외인 "최종 상품별 총 주문금액", 채널 이름은 3번 데이터와 같게
  label: "네이버스토어 주문내역 원본", channel: "네이버스토어",
  need: ["상품주문번호", "주문일시", "상품명", "수량", "최종 상품별 총 주문금액"],
  cols: { date: "주문일시", product: "상품명", units: "수량", revenue: "최종 상품별 총 주문금액" },
  exclude: [["주문상태", /취소|반품/], ["클레임상태", /(취소|반품)완료/]], // 반품요청 등 진행 중은 아직 매출
}];

function readMarket(name, table, head, m) {
  const at = (cells, col) => (cells[head.indexOf(col)] ?? "").trim();
  const num = (v) => v.replace(/,/g, ""); // "23,900" → 23900
  const errors = [], rows = [];
  let excluded = 0;
  if (table.length === 1) return { rows: [], errors: [`${name}: 데이터가 없습니다 (제목 행만 있음).`] };
  for (let i = 1; i < table.length && errors.length < MAX_ERRORS; i++) {
    const line = i + 1, cells = table[i];
    if (cells.length !== head.length) {
      errors.push(`${name} ${line}행: 칸 수가 제목(${head.length}칸)과 다릅니다 (${cells.length}칸).`);
      continue;
    }
    if (m.exclude.some(([col, re]) => re.test(at(cells, col)))) { excluded++; continue; }
    const raw = at(cells, m.cols.date);
    const date = raw.slice(0, 10).replace(/[./]/g, "-");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) errors.push(`${name} ${line}행 ${m.cols.date}: 날짜 형식(YYYY-MM-DD)이 아닙니다 — "${raw}"`);
    if (!at(cells, m.cols.product)) errors.push(`${name} ${line}행 ${m.cols.product}: 비어 있습니다.`);
    for (const k of ["units", "revenue"]) {
      const v = at(cells, m.cols[k]);
      if (!isNumber(num(v))) errors.push(`${name} ${line}행 ${m.cols[k]}: 0 이상의 숫자가 아닙니다 — "${v}"`);
    }
    rows.push({ date, product: at(cells, m.cols.product), channel: m.channel,
      revenue: num(at(cells, m.cols.revenue)), units: num(at(cells, m.cols.units)), purchases: "1" });
  }
  if (!errors.length && !rows.length) errors.push(`${name}: 매출로 셀 주문이 없습니다 (취소 · 반품 ${excluded}건 제외).`);
  if (errors.length) return { rows: [], errors, excluded };
  return { rows, errors, excluded, note: `${m.label} ${rows.length}건${excluded ? ` (취소 · 반품 ${excluded}건 제외)` : ""}` };
}

// RFC 4180 방식: 따옴표로 감싼 칸 안의 쉼표 · 줄바꿈은 칸의 일부, "" 는 따옴표 하나
export function parseCSV(text) {
  const src = text.replace(/^﻿/, "");
  const rows = [];
  let row = [], cell = "", quoted = false;
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (quoted) {
      if (c === '"') {
        if (src[i + 1] === '"') { cell += '"'; i++; } else quoted = false;
      } else cell += c;
    } else if (c === '"' && cell === "") quoted = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && src[i + 1] === "\n") i++;
      row.push(cell); rows.push(row); row = []; cell = "";
    } else cell += c;
  }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
  return rows.filter((r) => !(r.length === 1 && r[0].trim() === ""));
}

const looksBinary = (text) => /\u0000/.test(text.slice(0, 2000));
const isNumber = (v) => v.trim() !== "" && Number.isFinite(Number(v)) && Number(v) >= 0;

// 파일 한 개 → { rows, errors }
export function readTable(name, text) {
  if (looksBinary(text)) return { rows: [], errors: [`${name}: CSV 파일이 아닙니다.`] };
  const table = parseCSV(text);
  if (table.length === 0) return { rows: [], errors: [`${name}: 빈 파일입니다.`] };
  const head = table[0].map((h) => h.trim());
  const market = MARKET_FORMATS.find((m) => m.need.every((k) => head.includes(k)));
  if (market) return readMarket(name, table, head, market);
  const missing = REQUIRED.filter((k) => !head.includes(k));
  if (missing.length && looksRawExport(head)) {
    return { rows: [], rawExport: true, errors: [`${name}: 제목 줄이 한국어라 마켓 주문내역 원본으로 보입니다 — 이 툴은 원본을 바로 읽지 못합니다.`] };
  }
  if (missing.length) return { rows: [], errors: [`${name}: 필수 열이 없습니다 — ${missing.join(", ")}`] };
  const numbers = NUMBER_COLUMNS.filter((k) => head.includes(k)); // 있는 숫자 열만 검사
  if (!numbers.length) return { rows: [], errors: [`${name}: 숫자 열이 하나도 없습니다 — ${NUMBER_COLUMNS.join(", ")} 중 하나 이상 필요`] };
  if (table.length === 1) return { rows: [], errors: [`${name}: 데이터가 없습니다 (제목 행만 있음).`] };

  const errors = [];
  const rows = [];
  for (let i = 1; i < table.length && errors.length < MAX_ERRORS; i++) {
    const line = i + 1; // 엑셀에서 보이는 행 번호 (제목 = 1행)
    const cells = table[i];
    if (cells.length !== head.length) {
      errors.push(`${name} ${line}행: 칸 수가 제목(${head.length}칸)과 다릅니다 (${cells.length}칸).`);
      continue;
    }
    const r = Object.fromEntries(head.map((k, j) => [k, cells[j].trim()]));
    if (!/^\d{4}-\d{2}-\d{2}$/.test(r.date)) errors.push(`${name} ${line}행 date: 날짜 형식(YYYY-MM-DD)이 아닙니다 — "${r.date}"`);
    for (const k of numbers) {
      if (!isNumber(r[k])) errors.push(`${name} ${line}행 ${k}: 0 이상의 숫자가 아닙니다 — "${r[k]}"`);
    }
    rows.push(r);
  }
  return { rows: errors.length ? [] : rows, errors };
}

// File 여러 개 → { rows, files: [{name, rows}], errors }
export async function readFiles(files) {
  const list = [...files];
  if (!list.length) return { rows: [], files: [], errors: ["파일을 고르지 않았습니다."] };
  const out = { rows: [], files: [], errors: [] };
  for (const f of list) {
    if (!/\.csv$/i.test(f.name) && !/csv|text\/plain/.test(f.type)) {
      out.errors.push(`${f.name}: CSV 파일이 아닙니다.`);
      continue;
    }
    const { rows, errors, rawExport, note } = readTable(f.name, await f.text());
    out.errors.push(...errors);
    if (rawExport) out.rawExport = true;
    if (note) (out.notes ??= []).push(note);
    out.files.push({ name: f.name, rows: rows.length });
    out.rows.push(...rows);
  }
  if (out.rawExport) out.errors.push(RAW_EXPORT_GUIDE);
  if (out.errors.length) out.rows = [];
  return out;
}
