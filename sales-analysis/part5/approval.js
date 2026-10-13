/**
 * [담당5] 계획 승인 화면 — 과제 Step 3 "계획 제안 → 승인 → 실행 → 실행 기록"
 *
 * 질문 클릭·Enter 를 먼저(capture 단계) 받아 계획 카드를 띄우고,
 * [승인]을 눌렀을 때만 app.js 의 window.dashboard.analyze(q) 로 AI 서버를 부른다. [취소]면 부르지 않는다.
 * 계획 카드는 숫자를 만들지 않는다 — 행 수·기간처럼 데이터에서 그대로 세는 값만 쓴다.
 * AI 계획: setPlanProvider((signal, {question, rows, period}) => fetch(…)) 로 등록하면
 *   status-card.js 의 로딩 · 실패 화면을 거쳐 AI 계획(steps[].desc)을 보여 준다.
 *   실패하면 [규칙 기반 계획으로 계속] 으로 아래 planFor() 계획을 쓸 수 있다. 등록 안 하면 planFor() 그대로.
 */
(() => {
  const answerEl = document.getElementById("answer");
  const questionEl = document.getElementById("question");
  if (!answerEl || !questionEl) return;

  const planEl = document.createElement("div");
  planEl.id = "plan";
  planEl.setAttribute("aria-live", "polite");
  answerEl.before(planEl);

  let pending = null;
  let planProvider = null;
  window.setPlanProvider = (fn) => { planProvider = typeof fn === "function" ? fn : null; };

  const BADGE = { rule: "규칙 기반 계획", ai: "AI 계획", mock: "목업 계획" };

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // app.js 가 불러온 CSV 행
  const rowsNow = () => window.dashboard?.rows?.() ?? null;

  // 계산은 이미 4번 엔진(buildResult)이 끝냈다 — 계획은 "어떤 계산 결과를 보고, AI 에 무엇을 묻는지"를 적는다
  const DIAG = ["unit_price", "competitor_min_price"];
  // 필요한 열이 CSV에 없으면 그 단계는 계산 불가라고 계획에 미리 적는다
  function markGaps(steps) {
    const gaps = window.dashboard?.gaps?.() ?? {};
    return steps.map((s) => {
      const why = (s.needs || []).map((c) => gaps[c]).filter(Boolean);
      return why.length ? { ...s, do: `${s.do} — 계산 불가로 넘김 (근거: ${why.join(" · ")})` } : s;
    });
  }

  function planFor(q) {
    const base = [
      { do: "올린 CSV를 합쳐 월별로 묶고, 최근 두 달(전월 · 이번 달)을 비교한다", tool: "buildResult → monthly_kpis · changes" },
    ];
    const ai = { do: "계산 결과만 AI에 보내 확인된 사실 · 원인 후보(확정 아님) · 실행 제안 · 한계를 받는다 (AI는 숫자를 다시 계산하지 않음)", tool: "AI 서버 analyze-shop" };
    if (q.includes("채널")) {
      return [...base,
        { do: "판매 채널(쿠팡 · 네이버스토어 · 자사몰)별 ROAS · 구매전환율을 두 달 비교한다", tool: "channel_kpis" }, ai];
    }
    if (q.includes("상품")) {
      return [...base,
        { do: "쿠팡에서 경쟁 최저가가 우리보다 낮은 제품 목록을 확인한다", tool: "diagnostics", needs: DIAG },
        { do: "채널별 변화와 함께 먼저 볼 제품을 고른다", tool: "channel_kpis" }, ai];
    }
    if (q.includes("전환율")) {
      return [...base,
        { do: "방문 → 장바구니 → 구매 단계별 비율(장바구니율 · 장바구니→구매율)을 두 달 비교한다", tool: "monthly_kpis", needs: ["add_to_cart"] },
        { do: "전환율이 가장 많이 떨어진 채널을 찾는다", tool: "channel_kpis" }, ai];
    }
    if (q.includes("지표") || q.includes("먼저")) {
      return [...base,
        { do: "전월 대비 변화가 가장 큰 지표를 고른다", tool: "changes" }, ai];
    }
    return [...base,
      { do: "광고비 → 방문 → 구매 → 매출 순서로 변화율을 이어 보고, 가장 많이 떨어진 채널을 찾는다", tool: "changes · channel_kpis" },
      { do: "경쟁가 진단 결과를 함께 본다", tool: "diagnostics", needs: DIAG }, ai];
  }

  // AI 계획 응답(화면연결_데이터모양 ②) → 화면용 단계. desc 가 없으면 do 도 받는다.
  function stepsFrom(data) {
    const list = Array.isArray(data) ? data : data?.steps;
    if (!Array.isArray(list)) return [];
    return list
      .map((s) => ({ do: String(s?.desc ?? s?.do ?? "").trim(), tool: String(s?.tool ?? "").trim() }))
      .filter((s) => s.do);
  }

  function propose(q) {
    q = (q || "").trim();
    if (!q) return;
    window.cancelRequest?.(planEl);
    window.cancelRequest?.(answerEl);
    answerEl.innerHTML = "";

    const rows = rowsNow();
    if (!rows) {
      pending = null;
      planEl.innerHTML = `<div class="plan-card plan-notice">먼저 샘플 데이터나 CSV를 불러오세요. 불러온 데이터가 있어야 계획을 세울 수 있습니다.</div>`;
      return;
    }

    // 비교 기간은 4번 엔진 결과를 따른다 (바로 앞 달이 없으면 previousPeriod 가 null)
    const res = window.dashboard?.result?.();
    const cur = res?.currentPeriod, prev = res?.previousPeriod;
    const period = prev ? `${prev} → ${cur}` : cur ? `${cur} (비교할 바로 앞 달 없음)` : "기간 없음";
    const show = (steps, source) => showPlan({ q, steps, rows: rows.length, period, twoMonths: !!prev }, source);

    if (!planProvider || typeof window.runRequest !== "function") return show(markGaps(planFor(q)), "rule");

    pending = null;
    window.runRequest(planEl, (signal) => planProvider(signal, { question: q, rows: rows.length, period }), {
      label: "AI가 분석 계획을 세우는 중",
      onSuccess: (data) => {
        const steps = stepsFrom(data);
        if (!steps.length) throw new Error("steps 가 없습니다");
        show(steps, data?.source === "mock" ? "mock" : "ai");
      },
      extra: [{ label: "규칙 기반 계획으로 계속", onClick: () => show(markGaps(planFor(q)), "rule") }],
    });
  }

  function showPlan(p, source) {
    const { q, steps, rows, period } = p;
    pending = p;
    planEl.innerHTML = `
      <div class="plan-card" role="region" aria-label="분석 계획">
        <div class="plan-head">
          <h3>분석 계획 확인</h3>
          <span class="plan-badge plan-src-${source}">${BADGE[source]}</span>
        </div>
        <p class="plan-q">질문: <b>${esc(q)}</b></p>
        <ol class="plan-steps">
          ${steps.map((s) => `<li><span class="plan-do">${esc(s.do)}</span><code>${esc(s.tool)}</code></li>`).join("")}
        </ol>
        <p class="plan-data">사용할 데이터: <b>${rows}행</b> · 비교 기간 <b>${esc(period)}</b></p>
        ${pending.twoMonths ? "" : `<p class="plan-warn">전월 비교에는 바로 앞 달 데이터가 필요합니다(연속된 두 달). 승인해도 전월 대비 결과는 나오지 않습니다.</p>`}
        <div class="plan-actions">
          <button type="button" class="plan-approve">승인하고 분석</button>
          <button type="button" class="plan-cancel">취소</button>
        </div>
      </div>`;
    planEl.querySelector(".plan-approve").focus();
  }


  // AI 를 기다리는 동안에는 질문 입구(FAQ · 분석하기 · Enter)를 잠근다 — 새 계획을 또 승인하면
  // 앞 요청이 이미 서버에서 한도를 뺀 뒤라 1회가 더 줄어든다(발표 중 두 번 누르기 사고 방지)
  let busy = false;
  function setBusy(on) {
    busy = on;
    document.querySelectorAll("#ask, .faq-btn").forEach((b) => { b.disabled = on; });
    questionEl.readOnly = on;
    document.getElementById("ask")?.setAttribute("aria-busy", on ? "true" : "false");
  }

  async function approve() {
    if (!pending || busy) return;
    const p = pending;
    pending = null;
    const at = new Date();
    planEl.innerHTML = `<div class="plan-card plan-done">✓ 계획 승인됨 · ${at.toLocaleTimeString("ko-KR")} · ${esc(p.q)}</div>`;
    setBusy(true);
    try {
      // 여기서만 AI 를 부른다 (승인 전에는 0회)
      if (window.dashboard?.analyze) await window.dashboard.analyze(p.q);
    } finally {
      setBusy(false);
    }
  }


  function cancel() {
    if (!pending) return;
    pending = null;
    answerEl.innerHTML = "";
    planEl.innerHTML = `<div class="plan-card plan-cancelled">계획을 취소했습니다. 계산은 실행하지 않았습니다. 질문을 바꾸거나 다시 눌러 주세요.</div>`;
  }

  function reset() {
    window.cancelRequest?.(planEl);
    window.cancelRequest?.(answerEl);
    pending = null;
    setBusy(false);
    planEl.innerHTML = "";
  }

  // 질문 입구 세 곳(FAQ 버튼 · 분석하기 · Enter)을 app.js 보다 먼저 받는다
  document.addEventListener("click", (e) => {
    const t = e.target;
    if (t.closest(".plan-approve")) return approve();
    if (t.closest(".plan-cancel")) return cancel();
    const faq = t.closest(".faq-btn");
    const ask = t.closest("#ask");
    if (!faq && !ask) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    if (busy) return;
    if (faq) questionEl.value = faq.textContent.trim();
    propose(questionEl.value);
  }, true);

  document.addEventListener("keydown", (e) => {
    if (e.target !== questionEl || e.key !== "Enter" || e.isComposing) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    if (busy) return;
    propose(questionEl.value);
  }, true);

  // 새 데이터를 불러오면 이전 계획 · 답변을 지운다
  document.getElementById("sample")?.addEventListener("click", reset);
  document.getElementById("file")?.addEventListener("change", reset);
})();
