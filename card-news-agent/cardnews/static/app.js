// 카드뉴스 워크플로 화면. 서버 상태(GET /api/projects/{id})를 그대로 그린다.
"use strict";

const ACTIVE = new Set(["researching", "running"]);
const STATUS_LABEL = {
  created: "만듦",
  researching: "조사 중",
  candidates_ready: "후보 고르기",
  running: "작업 중",
  waiting_for_user: "답변 기다리는 중",
  editorial_ready: "편집 방향 정리됨",
  storyboard_ready: "스토리보드 승인 기다리는 중",
  images_ready: "그림 완료",
  failed: "실패",
  interrupted: "중단됨",
  cancelled: "취소됨",
};

const app = document.getElementById("app");
const banner = document.getElementById("mock-banner");
const enginePill = document.getElementById("engine-pill");

let health = null;
let pollTimer = null;
let lastJson = "";
let logOpen = false;
const picks = {}; // questionId -> {optionId, text}: 다시 그려도 고른 답이 남게 한다

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const rid = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random());

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch (_) { data = null; }
  return { ok: res.ok, status: res.status, data };
}
const errMsg = (r) => (r.data && r.data.error ? r.data.error.message : `요청 실패 (${r.status})`);

function setMockBanner(isMock) {
  banner.hidden = !isMock;
}

function engineWarning() {
  if (!health || health.engineReady !== false) return "";
  return `<div class="box bad"><b>실행 엔진을 쓸 수 없습니다.</b> ${esc(health.engineNote)}</div>`;
}

// ---------- 라우팅 ----------

async function route() {
  clearTimeout(pollTimer);
  lastJson = "";
  const m = location.hash.match(/^#\/p\/(prj_\w+)/);
  if (!health) {
    const r = await api("GET", "/api/health");
    health = r.data;
    enginePill.textContent = health ? `엔진: ${health.engine}${health.engineReady === false ? " ⚠ 로그인 필요" : ""}` : "";
  }
  if (m) await showProject(m[1]);
  else await showHome();
}
window.addEventListener("hashchange", route);

// ---------- 첫 화면 ----------

async function showHome() {
  setMockBanner(health && health.mock);
  const r = await api("GET", "/api/projects");
  const projects = (r.data && r.data.projects) || [];
  app.innerHTML = `
    ${engineWarning()}
    <h1>새 카드뉴스 만들기</h1>
    <form id="new" class="box">
      <label class="field" for="topic">주제</label>
      <input type="text" id="topic" required maxlength="200" placeholder="예: AI 최신소식 / 강사료 자동 계산 프로그램 소개">
      <label class="field" for="source">자료 위치 (선택)</label>
      <input type="text" id="source" placeholder="내 자료로 만들 때: 폴더 경로 (예: C:\\Users\\...\\gangsa-hours)">
      <div class="muted">비워 두면 웹에서 조사합니다. 경로를 넣으면 그 자료를 먼저 읽습니다.</div>
      <label class="field" for="direction">편집 방향 (선택)</label>
      <textarea id="direction" placeholder="예: 코딩을 모르는 학원 원장님에게 강사료 자동 계산을 소개하고 싶어."></textarea>
      <div class="muted">독자를 적어 두면 앱이 독자를 다시 묻지 않습니다.</div>
      <label class="field" for="period">조사 기간</label>
      <select id="period"><option value="7">최근 7일</option><option value="30">최근 30일</option></select>
      <div class="row"><button type="submit" id="create">만들고 조사 시작</button></div>
      <div id="new-err" class="err"></div>
    </form>
    <h2>프로젝트 목록</h2>
    ${projects.length ? `<table class="list"><tr><th>주제</th><th>상태</th><th>엔진</th><th>만든 시각</th></tr>
      ${projects.map((p) => `<tr><td><a href="#/p/${p.id}">${esc(p.topic)}</a></td>
        <td>${esc(STATUS_LABEL[p.status] || p.status)}</td><td>${esc(p.engine)}</td><td>${esc(p.createdAt)}</td></tr>`).join("")}
      </table>` : `<p class="muted">아직 프로젝트가 없습니다.</p>`}
  `;
  document.getElementById("new").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("create");
    btn.disabled = true;
    const body = {
      topic: document.getElementById("topic").value,
      sourcePath: document.getElementById("source").value,
      direction: document.getElementById("direction").value,
      periodDays: Number(document.getElementById("period").value),
    };
    const r1 = await api("POST", "/api/projects", body);
    if (!r1.ok) { document.getElementById("new-err").textContent = errMsg(r1); btn.disabled = false; return; }
    const pid = r1.data.projectId;
    await api("POST", `/api/projects/${pid}/research`, { requestId: rid() });
    location.hash = `#/p/${pid}`;
  });
}

// ---------- 프로젝트 화면 ----------

async function showProject(pid) {
  const r = await api("GET", `/api/projects/${pid}`);
  if (!r.ok) { app.innerHTML = `<div class="box bad">${esc(errMsg(r))}</div><a href="#/">← 처음으로</a>`; return; }
  const json = JSON.stringify(r.data);
  if (json !== lastJson) { // 내용이 바뀔 때만 다시 그린다(버튼이 계속 다시 그려지지 않게)
    lastJson = json;
    renderProject(r.data);
  }
  if (ACTIVE.has(r.data.status)) pollTimer = setTimeout(() => showProject(pid), 1200);
}

function renderProject(p) {
  setMockBanner(p.engine === "mock" || (p.research && p.research.mock));
  app.innerHTML = `
    <a href="#/" class="muted">← 처음으로</a>
    <h1>${esc(p.topic)} <span class="pill status-${esc(p.status)}">${esc(STATUS_LABEL[p.status] || p.status)}</span></h1>
    <div class="muted">엔진: ${esc(p.engine)} · 프로젝트 ${esc(p.id)}
      ${p.sourcePath ? ` · 자료: ${esc(p.sourcePath)}${p.sourceExists === false ? " (경로를 찾지 못함)" : ""}` : ""}
      ${p.direction ? `<br>편집 방향: ${esc(p.direction)}` : ""}</div>
    ${p.engine === (health && health.engine) ? engineWarning() : ""}
    ${errorBox(p)}
    ${activeBox(p)}
    ${researchSection(p)}
    ${answersSection(p)}
    ${questionSection(p)}
    ${editorialSection(p)}
    ${storyboardSection(p)}
    <details id="log" ${logOpen ? "open" : ""}><summary>작업 진행 내역 (${(p.events || []).length})</summary>
      <div class="log">${(p.events || []).slice().reverse().map((e) => `<div>${esc(e.at)} — ${esc(e.message)}</div>`).join("")}</div>
    </details>
  `;
  bindProject(p);
}

function errorBox(p) {
  if (!p.error) return "";
  return `<div class="box bad"><b>${esc(STATUS_LABEL[p.status] || "오류")}</b> — ${esc(p.error.message)}
    <div class="muted">오류 종류: ${esc(p.error.code)}</div>
    <div class="row"><button id="retry">다시 시도</button></div></div>`;
}

function activeBox(p) {
  if (!ACTIVE.has(p.status)) return "";
  const run = p.activeRun || {};
  const last = (p.events || []).slice(-1)[0];
  return `<div class="box">⏳ ${esc(STATUS_LABEL[p.status])}… (${esc(run.kind || "")}, 시작 ${esc(run.startedAt || "")})
    <div class="muted">${esc(last ? last.message : "")}</div>
    <div class="row"><button class="secondary" id="cancel" data-run="${esc(run.id || "")}">작업 취소</button></div></div>`;
}

function researchSection(p) {
  const res = p.research;
  if (!res) return "";
  const sel = new Set((p.selection && p.selection.candidateIds) || []);
  const locked = p.status !== "candidates_ready";
  const few = res.candidates.length < 7;
  return `
    <h2>1. 후보 고르기 <span class="muted">(1~3개)</span></h2>
    <div class="box ${res.mock ? "warn" : ""}">
      조사 기준 시각: <b>${esc(res.researchedAt)}</b> ${esc(res.timezone || "")}<br>
      조사 기간: <b>${esc(res.periodStart)} ~ ${esc(res.periodEnd)}</b> (최근 ${esc(res.periodDays)}일)
      ${res.sourcePath ? `<br>자료 위치: ${esc(res.sourcePath)}` : ""}
      ${res.note ? `<br><b>${esc(res.note)}</b>` : ""}
      ${traceLine(res.trace, res.costUsd)}
    </div>
    ${few && !locked ? `<div class="box warn">기간 안에서 후보를 ${res.candidates.length}개만 찾았습니다.
      ${res.periodDays < 30 ? `<div class="row"><button class="secondary" id="widen">30일로 넓혀 다시 조사</button></div>` : ""}</div>` : ""}
    <div class="candidates">
      ${res.candidates.map((c) => `
        <label class="cand ${sel.has(c.id) ? "checked" : ""}">
          <input type="checkbox" class="pick" value="${esc(c.id)}" ${sel.has(c.id) ? "checked" : ""}
            ${locked || (!sel.has(c.id) && sel.size >= 3) ? "disabled" : ""}>
          <div><div class="t">${esc(c.title)}
              ${c.sourceRead === true ? `<span class="badge">원문 읽음</span>` : c.sourceRead === false ? `<span class="badge no">원문 못 읽음</span>` : ""}</div>
            <div>${esc(c.summary)}</div>
            <dl><dt>게시일</dt><dd>${esc(c.date || "미확인")}</dd>
              ${c.eventDate ? `<dt>발표·변경일</dt><dd>${esc(c.eventDate)}</dd>` : ""}
              <dt>출처</dt><dd>${/^https?:/.test(c.source || "") ? `<a href="${esc(c.source)}" target="_blank" rel="noopener">${esc(c.source)}</a>` : esc(c.source)}</dd>
              <dt>고를 가치</dt><dd>${esc(c.value)}</dd><dt>불확실성</dt><dd>${esc(c.uncertainty)}</dd></dl></div>
        </label>`).join("")}
    </div>
    ${locked ? `<p class="muted">선택을 확정했습니다: ${[...sel].map(esc).join(", ")}</p>` :
      `<div class="row"><button id="confirm" ${sel.size ? "" : "disabled"}>선택한 ${sel.size}개로 다음 단계</button>
       <span class="muted">고른 후보는 바로 저장되어 새로고침해도 남습니다.</span></div>`}
    <div id="sel-err" class="err"></div>`;
}

function answersSection(p) {
  if (!p.answers || !p.answers.length) return "";
  return `<h2>답한 질문</h2><table><tr><th>질문</th><th>내 답</th><th>답한 시각</th></tr>
    ${p.answers.map((a) => `<tr><td>${esc(a.question)}</td><td>${esc(a.label)}</td><td>${esc(a.answeredAt)}</td></tr>`).join("")}</table>`;
}

function questionSection(p) {
  const q = p.question;
  if (!q || p.status !== "waiting_for_user") return "";
  const pick = picks[q.id] || {};
  return `
    <h2>2. 질문에 답하기</h2>
    <div class="box warn">
      <b>${esc(q.question)}</b>
      <div class="muted">${esc(q.why || "")}</div>
      <form id="qform" data-qid="${esc(q.id)}" data-version="${esc(q.version)}">
        ${q.options.map((o) => `
          <label class="opt ${pick.optionId === o.id ? "on" : ""}">
            <input type="radio" name="opt" value="${esc(o.id)}" ${pick.optionId === o.id ? "checked" : ""}>
            <b>${esc(o.label)}</b>${q.recommended === o.id ? `<span class="badge">추천</span>` : ""}
            <div class="muted">${esc(o.desc || "")}</div>
          </label>`).join("")}
        ${q.allowFree ? `<label class="opt ${pick.optionId === "__free" ? "on" : ""}">
            <input type="radio" name="opt" value="__free" ${pick.optionId === "__free" ? "checked" : ""}> <b>직접 입력</b>
            <input type="text" id="free" value="${esc(pick.text || "")}" placeholder="원하는 답을 적어 주세요">
          </label>` : ""}
        ${q.recommended ? `<div class="muted">추천 이유: ${esc(q.recommendReason || "")} — 추천은 미리 선택되지 않습니다. 직접 골라 주세요.</div>` : ""}
        <div class="row"><button type="submit" id="answer" ${pick.optionId ? "" : "disabled"}>답변 제출</button>
          <span class="muted">질문 ${esc(q.id)} · 버전 ${esc(q.version)}</span></div>
        <div id="q-err" class="err"></div>
      </form>
    </div>`;
}

function traceLine(t, cost) {
  if (!t) return "";
  const list = (title, xs) => xs && xs.length ? `<div><b>${title}</b><ul>${xs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "";
  return `<details class="trace"><summary>조사 기록: 검색 ${t.searches.length}회 · 원문 ${t.fetched.length}개 · 파일 ${t.files.length}개
      ${cost != null ? ` · 비용 약 $${Number(cost).toFixed(3)}` : ""}</summary>
    ${list("검색어", t.searches)}${list("읽은 원문", t.fetched)}${list("읽은 파일", t.files)}</details>`;
}

function srcLink(s) {
  return /^https?:/.test(s || "") ? `<a href="${esc(s)}" target="_blank" rel="noopener">${esc(s)}</a>` : esc(s);
}

function editorialSection(p) {
  const e = p.editorial;
  if (!e) return "";
  const hook = (h) => (typeof h === "string" ? esc(h) : `${esc(h.text)} <div class="muted">근거: ${esc(h.basis)}</div>`);
  const items = (xs) => (xs && xs.length ? `<ul>${xs.map((x) => `<li>${esc(x.text)} <span class="muted">— ${srcLink(x.source)}</span></li>`).join("")}</ul>` : `<p class="muted">없음</p>`);
  const v = e.verification;
  return `<h2>3. 편집 방향</h2><div class="box ${e.mock ? "warn" : "ok"}">
    독자: <b>${esc(e.audience)}</b> <span class="muted">${esc(e.audienceSource ? `(${e.audienceSource})` : "")}</span>
    ${e.audienceReason ? `<div class="muted">${esc(e.audienceReason)}</div>` : ""}
    ${e.purpose ? `<div>읽고 나서 할 행동: ${esc(e.purpose)}</div>` : ""}
    <div style="margin-top:8px">추천 형식: <b>${esc(e.format)}</b> ${e.formatReason ? `<span class="muted">— ${esc(e.formatReason)}</span>` : ""}</div>
    ${e.formatCompare ? `<table><tr><th>형식</th><th>장점</th><th>단점</th></tr>${e.formatCompare.map((f) =>
      `<tr><td>${esc(f.format)}</td><td>${esc(f.pros)}</td><td>${esc(f.cons)}</td></tr>`).join("")}</table>` : ""}
    <div style="margin-top:8px">표지 문장 후보:</div><ul>${(e.hooks || []).map((h) => `<li>${hook(h)}</li>`).join("")}</ul>
    <div class="muted">${esc(e.note || "")}</div></div>
    ${v ? `<h2>4. 심층 검증</h2><div class="box">
      <b>확인한 사실</b>${items(v.facts)}
      <b>발표 주체·운영자의 주장</b>${items(v.claims)}
      <b>아직 확인하지 못한 것</b>${items(v.unknown)}
      ${e.conflicts && e.conflicts.length ? `<b>자료끼리 다른 점</b><ul>${e.conflicts.map((c) => `<li>${esc(typeof c === "string" ? c : JSON.stringify(c))}</li>`).join("")}</ul>` : ""}
      ${traceLine(e.trace, e.costUsd)}</div>` : ""}`;
}

function storyboardSection(p) {
  const sb = p.storyboard;
  if (!sb) {
    if (p.status !== "editorial_ready") return "";
    return `<h2>5. 스토리보드</h2><div class="box"><div class="muted">편집 방향을 바탕으로 카드 5~8장의 설계도를 만듭니다. 승인하기 전에는 그림을 만들지 않습니다.</div>
      <div class="row"><button id="make-sb">스토리보드 만들기</button></div></div>`;
  }
  const st = sb.style || {};
  const approved = !!sb.approved;
  const swatches = (st.palette || []).map((c) => `<span class="sw" style="background:${/^#[0-9a-fA-F]{3,8}$/.test(c) ? c : "#ccc"}" title="${esc(c)}"></span>`).join("");
  return `<h2>5. 스토리보드 <span class="muted">버전 ${esc(sb.version)} · ${sb.cards.length}장 ·
      ${approved ? `승인함 (${esc(sb.approved.at)})` : "승인 전"}</span></h2>
    <div class="box ${sb.mock ? "warn" : ""}">
      형식: <b>${esc(sb.format || "")}</b> ${sb.reason ? `<span class="muted">— ${esc(sb.reason)}</span>` : ""}<br>
      공통 그림체: ${swatches} ${esc(st.illustration || "")} · ${esc(st.mood || "")} · ${esc(st.layout || "")}
      ${(p.storyboardFeedback || []).length ? `<div class="muted">반영한 변경 요청: ${p.storyboardFeedback.map(esc).join(" / ")}</div>` : ""}
    </div>
    <div class="sb-cards">${sb.cards.map((c) => sbCard(p, c, approved)).join("")}</div>
    ${!approved && p.status === "storyboard_ready" ? `
      <div class="box">
        <label class="field" for="sb-feedback">변경 요청 (카드 번호 + 문제 + 원하는 결과)</label>
        <textarea id="sb-feedback" placeholder="예: 4번 카드의 본문이 길어. 핵심 조건은 유지하고 두 문장으로 줄여 줘."></textarea>
        <div class="row"><button class="secondary" id="sb-change">변경 요청 보내기</button>
          <button id="sb-approve" data-version="${esc(sb.version)}">이대로 승인하고 그림 만들기</button></div>
        <div class="muted">승인하기 전에는 그림을 만들지 않습니다. 그림은 agy로 먼저 시도하고, 안 되면 claude cli 도형 그림으로 대신합니다.</div>
        <div id="sb-err" class="err"></div>
      </div>` : ""}`;
}

function sbCard(p, c, approved) {
  const img = c.image || {};
  let pic = "";
  if (approved) {
    if (img.status === "done") {
      pic = `<div class="pic"><img src="/api/projects/${esc(p.id)}/images/${esc(img.file)}" alt="카드 ${esc(c.no)} 그림 (생성 이미지)">
        <div class="tool ${img.tool === "agy" ? "" : "alt"}">${esc(img.toolLabel || img.tool)}</div>
        ${img.fallbackReason ? `<div class="muted">대신한 이유: ${esc(img.fallbackReason)}</div>` : ""}
        <div class="muted">${esc(img.format)} ${esc(img.width)}×${esc(img.height)} · ${esc(img.file)} · ${esc(img.kind || "")}</div>
        <details><summary class="muted">그림 요청문</summary><div class="muted">${esc(img.prompt)}</div></details>
        <button class="secondary small regen" data-no="${esc(c.no)}" ${ACTIVE.has(p.status) ? "disabled" : ""}>이 카드 그림 다시 만들기</button></div>`;
    } else if (img.status === "failed") {
      pic = `<div class="pic fail"><b>그림 실패</b><div>${esc(img.error)}</div>
        ${img.fallbackReason ? `<div class="muted">agy: ${esc(img.fallbackReason)}</div>` : ""}
        <button class="small regen" data-no="${esc(c.no)}" ${ACTIVE.has(p.status) ? "disabled" : ""}>이 카드 그림 다시 만들기</button></div>`;
    } else {
      pic = `<div class="pic wait">${img.status === "generating" ? "⏳ 그림 만드는 중…" : "차례를 기다리는 중"}</div>`;
    }
  }
  return `<div class="sb-card ${approved ? "with-pic" : ""}">
    ${pic}
    <div><div class="muted">#${esc(c.no)} · ${esc(c.role)}</div>
      <div class="t">${esc(c.title)}</div>
      <div><b>${esc(c.keyLine)}</b></div>
      <div>${esc(c.body)}</div>
      <dl><dt>그림 역할</dt><dd>${esc(c.imageRole)}</dd><dt>그림 계획</dt><dd>${esc(c.imagePlan)}</dd>
        <dt>출처</dt><dd>${(c.sources || []).map(srcLink).join("<br>")}</dd></dl>
      ${c.note ? `<div class="note">⚠ ${esc(c.note)}</div>` : ""}</div>
  </div>`;
}

function bindProject(p) {
  const pid = p.id;
  const reload = () => { lastJson = ""; clearTimeout(pollTimer); showProject(pid); };
  const log = document.getElementById("log");
  if (log) log.addEventListener("toggle", () => { logOpen = log.open; });

  const retry = document.getElementById("retry");
  if (retry) retry.onclick = async () => {
    retry.disabled = true;
    const r = await api("POST", `/api/projects/${pid}/retry`, { requestId: rid() });
    if (!r.ok) alert(errMsg(r));
    reload();
  };
  const cancel = document.getElementById("cancel");
  if (cancel) cancel.onclick = async () => {
    cancel.disabled = true;
    await api("POST", `/api/runs/${cancel.dataset.run}/cancel`);
    reload();
  };
  const widen = document.getElementById("widen");
  if (widen) widen.onclick = async () => {
    widen.disabled = true;
    const r = await api("POST", `/api/projects/${pid}/research`, { requestId: rid(), periodDays: 30 });
    if (!r.ok) alert(errMsg(r));
    reload();
  };

  const post = async (btn, path, body, errId) => {
    btn.disabled = true;
    const r = await api("POST", `/api/projects/${pid}/${path}`, Object.assign({ requestId: rid() }, body));
    if (!r.ok) {
      const box = errId && document.getElementById(errId);
      if (box) box.textContent = errMsg(r); else alert(errMsg(r));
      btn.disabled = false;
      return;
    }
    reload();
  };
  const makeSb = document.getElementById("make-sb");
  if (makeSb) makeSb.onclick = () => post(makeSb, "storyboard", {});
  const sbChange = document.getElementById("sb-change");
  if (sbChange) sbChange.onclick = () => {
    const fb = document.getElementById("sb-feedback").value.trim();
    if (!fb) { document.getElementById("sb-err").textContent = "변경 요청을 적어 주세요."; return; }
    post(sbChange, "storyboard", { feedback: fb }, "sb-err");
  };
  const sbApprove = document.getElementById("sb-approve");
  if (sbApprove) sbApprove.onclick = () =>
    post(sbApprove, "approve", { stage: "storyboard", version: Number(sbApprove.dataset.version) }, "sb-err");
  document.querySelectorAll(".regen").forEach((b) => { b.onclick = () => post(b, `cards/${b.dataset.no}/image`, {}); });

  const version = p.research && p.research.candidatesVersion;
  const saveSelection = async (confirm) => {
    const ids = [...document.querySelectorAll(".pick:checked")].map((x) => x.value);
    const r = await api("POST", `/api/projects/${pid}/selection`, { candidateIds: ids, version, confirm, requestId: rid() });
    if (!r.ok) document.getElementById("sel-err").textContent = errMsg(r);
    reload();
  };
  document.querySelectorAll(".pick").forEach((cb) => cb.addEventListener("change", () => saveSelection(false)));
  const confirmBtn = document.getElementById("confirm");
  if (confirmBtn) confirmBtn.onclick = () => { confirmBtn.disabled = true; saveSelection(true); };

  const form = document.getElementById("qform");
  if (form) {
    const qid = form.dataset.qid;
    const submit = document.getElementById("answer");
    const free = document.getElementById("free");
    const sync = () => {
      const on = form.querySelector("input[name=opt]:checked");
      picks[qid] = { optionId: on ? on.value : null, text: free ? free.value : "" };
      form.querySelectorAll(".opt").forEach((l) => l.classList.toggle("on", l.contains(on)));
      submit.disabled = !on || (on.value === "__free" && !picks[qid].text.trim());
    };
    form.addEventListener("change", sync);
    if (free) free.addEventListener("input", () => { form.querySelector("input[value=__free]").checked = true; sync(); });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (submit.disabled) return;
      submit.disabled = true; // 두 번 눌러도 한 번만 보낸다
      const pk = picks[qid];
      const answer = pk.optionId === "__free" ? { text: pk.text } : { optionId: pk.optionId };
      const r = await api("POST", `/api/projects/${pid}/answers`,
        { questionId: qid, version: Number(form.dataset.version), answer, requestId: rid() });
      if (!r.ok) { alert(errMsg(r)); }
      reload();
    });
  }
}

route();
