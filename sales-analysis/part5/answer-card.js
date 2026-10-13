/**
 * [담당5] 답변 카드 — PR #1 AI 답변 형식을 그린다.
 *   { summary, facts[], hypotheses[], actions[{priority, action, reason}], limitations[] }
 *
 * 사용: renderAnalysis(응답, { source: "ai" | "example", target: 요소 })
 *   - 응답은 객체 또는 JSON 문자열(```json 코드 블록으로 감싸져 있어도 됨)
 *   - target 을 안 주면 #answer 에 그린다
 *   - 돌려주는 값: { ok: true } 또는 { ok: false, reason }
 * AI 응답은 믿지 않는다 — 형식을 검사하고, 모든 글자는 HTML 이스케이프해서 그대로 보여 준다.
 */
(() => {
  const MAX_ACTIONS = 3;

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function parse(input) {
    if (input && typeof input === "object") return { ok: true, data: input };
    if (typeof input !== "string") return { ok: false, reason: "응답이 비어 있습니다." };
    const text = input.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
    try {
      const data = JSON.parse(text);
      if (!data || typeof data !== "object" || Array.isArray(data)) return { ok: false, reason: "JSON 객체가 아닙니다." };
      return { ok: true, data };
    } catch {
      return { ok: false, reason: "JSON 형식이 아닙니다." };
    }
  }

  // 문자열 배열로 정리 (문자열 하나면 배열로, 빈 값은 버림)
  const strList = (v) => (Array.isArray(v) ? v : v == null ? [] : [v])
    .map((x) => (x == null ? "" : typeof x === "object" ? JSON.stringify(x) : String(x)).trim())
    .filter(Boolean);

  function actionList(v) {
    const list = (Array.isArray(v) ? v : v == null ? [] : [v]).map((a, i) => {
      if (typeof a === "string") return { priority: Infinity, action: a, reason: "", i };
      const p = Number(a?.priority);
      return { priority: Number.isFinite(p) ? p : Infinity, action: String(a?.action ?? "").trim(), reason: String(a?.reason ?? "").trim(), i };
    }).filter((a) => a.action);
    return list.sort((a, b) => a.priority - b.priority || a.i - b.i);
  }

  const items = (list, cls) => list.length
    ? `<ul class="${cls}">${list.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
    : `<div class="ac-none">없음</div>`;

  function sourceBadge(source) {
    return source === "example"
      ? `<span class="ac-badge ac-src-example">예시 응답</span>`
      : `<span class="ac-badge ac-src-ai">AI 분석</span>`;
  }

  function errorCard(reason, raw, source) {
    const shown = typeof raw === "string" ? raw : (() => { try { return JSON.stringify(raw, null, 2); } catch { return String(raw); } })();
    return `
      <div class="ac ac-error" role="alert">
        <div class="ac-head">${sourceBadge(source)}</div>
        <div class="ac-summary">AI 응답 형식 오류</div>
        <div class="ac-reason">${esc(reason)} 계산 결과(위 KPI · 차트)는 그대로 믿어도 됩니다. 다시 질문하거나 잠시 뒤 시도해 주세요.</div>
        <details class="ac-raw"><summary>받은 내용 보기</summary><pre>${esc(String(shown ?? "").slice(0, 600))}</pre></details>
      </div>`;
  }

  function renderAnalysis(input, opts = {}) {
    const target = opts.target || document.getElementById("answer");
    const source = opts.source || "ai";
    if (!target) return { ok: false, reason: "그릴 자리(#answer)가 없습니다." };

    const parsed = parse(input);
    if (!parsed.ok) { target.innerHTML = errorCard(parsed.reason, input, source); return parsed; }

    const d = parsed.data;
    const summary = typeof d.summary === "string" ? d.summary.trim() : "";
    if (!summary) {
      const r = { ok: false, reason: "summary(한 문장 요약)가 없습니다." };
      target.innerHTML = errorCard(r.reason, d, source);
      return r;
    }

    const facts = strList(d.facts);
    const hyps = strList(d.hypotheses);
    const lims = strList(d.limitations);
    const acts = actionList(d.actions);
    const shownActs = acts.slice(0, MAX_ACTIONS);
    const more = acts.length - shownActs.length;

    target.innerHTML = `
      <div class="ac" data-source="${esc(source)}">
        <div class="ac-head">${sourceBadge(source)}</div>
        <div class="ac-summary">${esc(summary)}</div>

        <section class="ac-sec ac-facts">
          <h4>확인된 사실 <small>데이터에서 확인됨</small></h4>
          ${items(facts, "ac-list")}
        </section>

        <section class="ac-sec ac-hyps">
          <h4>원인 후보 <span class="ac-tag">확정 아님</span></h4>
          ${items(hyps, "ac-list")}
        </section>

        <section class="ac-sec ac-actions">
          <h4>실행 제안</h4>
          ${shownActs.length ? `<ol class="ac-acts">${shownActs.map((a, i) => `
            <li><span class="ac-pri">${i + 1}</span>
              <div><div class="ac-act">${esc(a.action)}</div>${a.reason ? `<div class="ac-why">근거: ${esc(a.reason)}</div>` : ""}</div>
            </li>`).join("")}</ol>` : `<div class="ac-none">없음</div>`}
          ${more > 0 ? `<div class="ac-more">외 ${more}개</div>` : ""}
        </section>

        <section class="ac-sec ac-lims">
          <h4>분석 한계</h4>
          ${items(lims, "ac-list")}
        </section>
      </div>`;
    return { ok: true };
  }

  window.renderAnalysis = renderAnalysis;
})();
