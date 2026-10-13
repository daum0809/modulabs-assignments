/**
 * [담당5] 로딩 · 실패 · 중단 화면 — AI 를 부르는 두 곳(계획 #plan · 답변 #answer)에서 같이 쓴다.
 *
 *   runRequest(자리, 요청함수, { label, timeoutMs, onSuccess, extra })
 *     요청함수(signal) 는 fetch 의 Response 또는 이미 꺼낸 JSON 을 돌려준다.
 *     로딩(경과 초 · [중단]) → 성공이면 onSuccess(데이터), 실패면 종류별 카드 + [다시 시도].
 *   runAnalysis(요청함수, { target, timeoutMs })
 *     답변 카드용. 응답의 analysis 가 #1 JSON 이면 renderAnalysis, 그냥 글이면 글 카드.
 *   postJSON(주소, 본문) → 요청함수   예) runAnalysis(postJSON(API_URL, { result, question }))
 *
 * 한 자리에 요청은 하나만: 새 요청이 오면 이전 요청을 취소하고, 늦게 온 이전 응답은 버린다.
 * 자동 재시도는 없다. 서버 오류 원문은 화면에 쓰지 않고 console.warn 으로만 남긴다.
 */
(() => {
  // 4번 AI 서버 응답은 7~27초(DevelopDoc/ANALYSIS_SUBMISSION.md §6) — 여유를 두고 60초까지 기다린다
  const SLOW_MS = 10000;    // 이만큼 지나면 "평소보다 오래 걸립니다"
  const TIMEOUT_MS = 60000; // 이만큼 지나면 자동 중단

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const TRUST = "계산 결과(위 KPI · 차트)는 코드가 계산한 값이라 그대로 믿어도 됩니다.";
  // 서버가 보낸 이유는 받은 그대로 두고, 아는 문구만 화면용 한국어로 바꾼다(원문은 괄호로 남겨 담당자가 찾게)
  // 4번 서버 형식: "OpenAI request failed." 또는 "OpenAI request failed (404): <OpenAI 가 보낸 이유>"(8f16578)
  const SERVER_MSG_KO = [
    [/^OpenAI request failed\b/, "AI 서비스(OpenAI)가 요청을 거절했습니다."],
  ];
  const serverMsgHtml = (m) => {
    const hit = SERVER_MSG_KO.find(([re]) => re.test(String(m).trim()));
    return hit ? `${esc(hit[1])} <span class="sc-server-raw">(${esc(m)})</span>` : esc(m);
  };

  const isSetup = (o) => o.code >= 400 && o.code < 500;
  const val = (v, o) => (typeof v === "function" ? v(o) : v);

  const FAIL = {
    timeout:   { title: "응답이 너무 오래 걸려 멈췄습니다", body: (o) => `${Math.round(o.timeoutMs / 1000)}초 안에 답이 오지 않아 요청을 멈췄습니다. 잠시 뒤 다시 시도해 주세요.` },
    network:   { title: "서버에 연결하지 못했습니다", body: () => "인터넷 연결을 확인하거나 잠시 뒤 다시 시도해 주세요." },
    auth:      { title: "로그인을 다시 확인해 주세요", body: () => "AI 서버가 요청을 거절했습니다(로그인 만료 또는 권한 없음). 다시 로그인한 뒤 시도해 주세요." },
    login:     { title: "로그인이 필요합니다", body: () => "AI 분석은 로그인한 사용자만 쓸 수 있습니다. 로그인한 뒤 다시 시도해 주세요. (지표와 차트는 로그인 없이도 볼 수 있습니다)" },
    // 4번 서버는 한도를 먼저 센 뒤 OpenAI 를 부른다 — 실패해도 1회가 줄어 있다
    // 400번대(401·403·429 제외)는 서버 설정 문제(예: OpenAI 거절)라 같은 요청을 다시 보내도 또 실패한다 → 다시 시도를 권하지 않는다
    server:    {
      title: (o) => (isSetup(o) ? "AI 서버 설정 문제" : "AI 서버 오류"),
      body: (o) => isSetup(o)
        ? `AI 서버가 요청을 처리하지 못했습니다 (코드 ${o.code}). 서버 설정 문제라 다시 시도해도 해결되지 않을 가능성이 큽니다. AI 서버 담당자에게 알려 주세요.`
        : `AI 서버에서 오류가 났습니다${o.code ? ` (코드 ${o.code})` : ""}. 잠시 뒤 다시 시도해 주세요.`,
      note: (o) => (isSetup(o) ? "다시 눌러도 오늘 AI 분석 횟수만 1회 더 줄어듭니다." : "다시 시도하면 오늘 AI 분석 횟수가 1회 더 줄어듭니다."),
      retry: (o) => (isSetup(o) ? { label: "그래도 다시 시도", ghost: true } : null),
    },
    app:       { title: "요청을 처리하지 못했습니다", body: (o) => o.message || "서버가 요청을 처리하지 못했습니다." },
    format:    { title: "응답 형식 오류", body: () => "AI 서버의 답을 읽을 수 없습니다. 다시 시도해 주세요." },
    cancelled: { title: "중단했습니다", body: () => "요청을 멈췄습니다. 질문을 바꾸거나 다시 시도해 주세요." },
    // 서버 429 — 하루 한도는 4번 AI 서버가 센다
    quota:     { title: "오늘 AI 분석 횟수를 다 썼습니다", body: () => "오늘 쓸 수 있는 AI 분석 횟수를 모두 썼습니다. 내일 다시 이용하거나 요금제를 올려 주세요.", noRetry: true },
  };

  const runs = new Map();    // 자리 → 진행 중인 요청
  const tickers = new Map(); // 자리 → 경과 초 타이머

  function stopTicker(target) {
    clearInterval(tickers.get(target));
    tickers.delete(target);
    target.removeAttribute("aria-busy");
  }

  function fail(kind, extra = {}) {
    return Object.assign(new Error(kind), { kind }, extra);
  }

  function renderLoading(target, { label = "AI가 분석하는 중", onCancel } = {}) {
    stopTicker(target);
    target.setAttribute("aria-busy", "true");
    target.innerHTML = `
      <div class="sc sc-loading">
        <div class="sc-row">
          <span class="sc-spin" aria-hidden="true"></span>
          <span class="sc-label" role="status">${esc(label)}…</span>
          <span class="sc-sec">0초</span>
          ${onCancel ? `<button type="button" class="sc-btn sc-btn-ghost sc-cancel">중단</button>` : ""}
        </div>
        <div class="sc-slow" hidden>평소보다 오래 걸립니다. 계속 기다리거나 [중단]을 누를 수 있습니다.</div>
        <div class="sc-skel" aria-hidden="true"><i></i><i></i><i></i></div>
      </div>`;
    if (onCancel) target.querySelector(".sc-cancel").addEventListener("click", onCancel);
    const started = Date.now();
    tickers.set(target, setInterval(() => {
      const card = target.querySelector(".sc-loading");
      if (!card) return stopTicker(target); // 다른 코드가 자리를 덮었다
      const ms = Date.now() - started;
      card.querySelector(".sc-sec").textContent = `${Math.floor(ms / 1000)}초`;
      if (ms >= SLOW_MS) card.querySelector(".sc-slow").hidden = false;
    }, 1000));
  }

  function renderFailure(target, kind, { detail = {}, onRetry, extra = [] } = {}) {
    stopTicker(target);
    const f = FAIL[kind] || FAIL.server;
    if (f.noRetry) onRetry = null; // 다시 눌러도 결과가 같은 실패
    const o = { timeoutMs: TIMEOUT_MS, ...detail };
    const retry = val(f.retry, o) || { label: "다시 시도", ghost: false };
    const note = val(f.note, o);
    const buttons = [
      onRetry ? `<button type="button" class="sc-btn${retry.ghost ? " sc-btn-ghost" : ""} sc-retry">${esc(retry.label)}</button>` : "",
      ...extra.map((b, i) => `<button type="button" class="sc-btn sc-btn-ghost sc-extra" data-i="${i}">${esc(b.label)}</button>`),
    ].join("");
    target.innerHTML = `
      <div class="sc sc-fail sc-${esc(kind)}" role="alert" data-kind="${esc(kind)}">
        <div class="sc-title">${esc(val(f.title, o))}</div>
        <div class="sc-body">${esc(f.body(o))}</div>
        ${detail.serverMessage ? `<div class="sc-server-msg">서버 메시지: ${serverMsgHtml(detail.serverMessage)}</div>` : ""}
        ${note && onRetry ? `<div class="sc-note">${esc(note)}</div>` : ""}
        <div class="sc-trust">${esc(TRUST)}</div>
        ${buttons ? `<div class="sc-actions">${buttons}</div>` : ""}
      </div>`;
    if (onRetry) target.querySelector(".sc-retry").addEventListener("click", onRetry);
    target.querySelectorAll(".sc-extra").forEach((el) => el.addEventListener("click", () => extra[el.dataset.i].onClick()));
  }

  // Response 면 상태 코드로 실패를 가리고 JSON 을 꺼낸다. 이미 꺼낸 값이면 그대로.
  async function readResponse(res) {
    const isResponse = res && typeof res === "object" && typeof res.text === "function" && "status" in res;
    if (!isResponse) return res;
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { /* 아래에서 처리 */ }
    if (!res.ok) {
      console.warn("[status-card] 서버 오류", res.status, data ?? text.slice(0, 300));
      // 429 = 4번 서버의 "오늘 무료 분석 횟수를 다 씀" (consume_analysis_quota)
      const kind = res.status === 429 ? "quota" : res.status === 401 || res.status === 403 ? "auth" : "server";
      // 서버가 보낸 이유({error} 또는 {detail:{error:{message}}}) — 담당자가 개발자 도구 없이 보게
      const msg = data?.error ?? data?.detail?.error?.message;
      throw fail(kind, { code: res.status, detail: typeof msg === "string" && msg ? { serverMessage: msg.slice(0, 200) } : {} });
    }
    if (data === null) throw fail("format");
    return data;
  }

  function aborted(signal) {
    return new Promise((_, reject) => signal.addEventListener("abort", () => reject(fail("aborted")), { once: true }));
  }

  function cancelRequest(target) {
    const run = runs.get(target);
    if (!run) return;
    runs.delete(target); // 먼저 지워서, 취소된 요청이 화면을 그리지 않게 한다
    run.ctrl.abort();
    stopTicker(target);
  }

  // 끝날 때마다(다시 시도 포함) 자리에 "sc:done" 이벤트를 보낸다 — 마지막 결과가 필요한 곳이 들을 수 있게
  async function runRequest(target, requestFn, opts = {}) {
    const r = await runOnce(target, requestFn, opts);
    if (target && r.kind !== "replaced") target.dispatchEvent(new CustomEvent("sc:done", { detail: r }));
    return r;
  }

  async function runOnce(target, requestFn, opts) {
    if (!target) return { ok: false, kind: "no-target" };
    cancelRequest(target);
    const ctrl = new AbortController();
    const run = { ctrl, why: null };
    runs.set(target, run);
    const timeoutMs = opts.timeoutMs ?? TIMEOUT_MS;
    const timer = setTimeout(() => { run.why = "timeout"; ctrl.abort(); }, timeoutMs);
    const mine = () => runs.get(target) === run;

    renderLoading(target, { label: opts.label, onCancel: () => { run.why = "cancelled"; ctrl.abort(); } });

    let data, kind, detail = {};
    try {
      const raw = await Promise.race([Promise.resolve().then(() => requestFn(ctrl.signal)), aborted(ctrl.signal)]);
      data = await Promise.race([readResponse(raw), aborted(ctrl.signal)]);
      if (data && typeof data === "object" && data.ok === false) {
        console.warn("[status-card] ok:false", data);
        throw fail("app", { detail: { message: typeof data.message === "string" ? data.message : "" } });
      }
    } catch (e) {
      kind = run.why || (e.kind && e.kind !== "aborted" ? e.kind : null) || (e.name === "AbortError" ? "cancelled" : "network");
      if (kind === "network") console.warn("[status-card] 연결 실패", e);
      detail = { ...e.detail, ...(e.code ? { code: e.code } : {}), ...(kind === "timeout" ? { timeoutMs } : {}) };
    }
    clearTimeout(timer);
    if (!mine()) return { ok: false, kind: "replaced" }; // 더 새 요청이 자리를 가져갔다
    runs.delete(target);
    stopTicker(target);

    if (!kind) {
      try {
        await opts.onSuccess?.(data);
        return { ok: true, data };
      } catch (e) {
        console.warn("[status-card] 응답 처리 실패", e);
        kind = "format";
      }
    }
    renderFailure(target, kind, {
      detail,
      onRetry: () => runRequest(target, requestFn, opts),
      extra: opts.extra || [],
    });
    return { ok: false, kind };
  }

  // AI 글에 흔한 마크다운(제목 · 목록 · 굵게)만 모양으로 바꾼다. 먼저 전부 이스케이프하므로 태그는 실행되지 않는다.
  // 제목 줄(# 제목 · **제목** 한 줄)이 아래 네 가지면 그 아래 목록까지 한 상자로 묶는다 — 사실 · 원인 후보 · 액션을 한눈에 구분
  const SECTIONS = [
    { kind: "facts", re: /확인된\s*사실|사실/, icon: "✓" },
    { kind: "hyps", re: /원인|후보|가설/, icon: "?", tag: "확정 아님" },
    { kind: "acts", re: /액션|행동|제안|실행|해야/, icon: "→" },
    { kind: "limits", re: /한계|주의|유의/, icon: "!" },
  ];
  function textToHTML(text) {
    const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    const out = [];
    let list = null; // "ul" | "ol"
    let sec = false;
    const close = () => { if (list) { out.push(`</${list}>`); list = null; } };
    const closeSec = () => { close(); if (sec) { out.push("</section>"); sec = false; } };
    for (const raw of String(text).split(/\r?\n/)) {
      const line = raw.trim();
      let m;
      if (!line) { close(); continue; }
      const head = (m = line.match(/^#{1,6}\s+(.*)$/)) ? m[1] : (m = line.match(/^\*\*([^*]{1,20})\*\*\s*:?$/)) ? m[1] : null;
      const hit = head ? SECTIONS.find((x) => x.re.test(head)) : null;
      if (hit) {
        closeSec();
        out.push(`<section class="sc-sec sc-sec-${hit.kind}"><h5 class="sc-sec-h"><span class="sc-sec-ico" aria-hidden="true"><img src="icons/${hit.kind}.png" alt="" onerror="this.remove()"><i class="sc-sec-fb">${hit.icon}</i></span>${inline(head.replace(/\*\*/g, ""))}${hit.tag ? `<em class="sc-sec-tag">${hit.tag}</em>` : ""}</h5>`);
        sec = true;
        continue;
      }
      if ((m = line.match(/^#{1,6}\s+(.*)$/))) { close(); out.push(`<h4 class="sc-md-h">${inline(m[1])}</h4>`); continue; }
      if ((m = line.match(/^[-*•]\s+(.*)$/)) || (m = line.match(/^\d+[.)]\s+(.*)$/))) {
        const kind = /^\d/.test(line) ? "ol" : "ul";
        if (list !== kind) { close(); out.push(`<${kind} class="sc-md-list">`); list = kind; }
        out.push(`<li>${inline(m[1])}</li>`);
        continue;
      }
      close();
      out.push(`<div class="sc-md-p">${inline(line)}</div>`); // p 는 팀 styles.css `#answer p` 카드 모양이 덮는다
    }
    closeSec();
    return out.join("");
  }

  function renderText(target, text) {
    target.innerHTML = `
      <div class="sc sc-text">
        <div class="sc-text-head"><span class="sc-badge">AI 분석</span><span class="sc-badge sc-badge-plain">글 답변</span></div>
        ${((h) => `<div class="sc-text-body${h.includes("sc-sec") ? " has-secs" : ""}">${h}</div>`)(textToHTML(text))}
        <div class="sc-note">숫자는 계산 코드가 만든 값이고, AI 는 그 결과를 해석했습니다. 원인은 확정이 아닙니다.</div>
      </div>`;
  }

  // 답변 카드: { analysis: "…" } 또는 #1 형식 객체를 받는다
  function runAnalysis(requestFn, opts = {}) {
    const target = opts.target || document.getElementById("answer");
    return runRequest(target, requestFn, {
      label: "AI가 결과를 해석하는 중",
      ...opts,
      onSuccess: (data) => {
        const a = data && typeof data === "object" && "analysis" in data ? data.analysis : data;
        if (a == null || (typeof a === "string" && !a.trim())) throw new Error("빈 응답");
        const looksJSON = typeof a === "object" || /^\s*(\{|```)/.test(a);
        if (looksJSON && typeof window.renderAnalysis === "function") {
          window.renderAnalysis(a, { target, source: "ai" }); // 형식이 깨졌으면 renderAnalysis 가 형식 오류 카드를 그린다
        } else {
          renderText(target, typeof a === "string" ? a : JSON.stringify(a, null, 2));
        }
      },
    });
  }

  const postJSON = (url, body) => (signal) => fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  Object.assign(window, { renderLoading, renderFailure, runRequest, runAnalysis, cancelRequest, postJSON });
})();
