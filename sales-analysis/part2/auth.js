/**
 * [담당2] 로그인 · 회원가입 · 로그아웃 (Supabase Auth)
 *
 * 붙이는 법 (페이지의 </body> 바로 앞, 다른 스크립트보다 먼저):
 *   <link rel="stylesheet" href="../part2/auth.css">
 *   <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
 *   <script src="../part2/config.js"></script>
 *   <script src="../part2/auth.js"></script>
 *
 * 붙이면 로그인하지 않은 사람에게는 로그인 화면만 보이고, 로그인하면 원래 화면과
 * 오른쪽 위 계정 표시(이메일 · 요금제 · 로그아웃)가 나타난다. 기존 파일은 고치지 않는다.
 * 로그인 상태는 브라우저(localStorage)에 저장되어 새로고침해도 유지된다.
 * 로그아웃하거나 다른 계정으로 바뀌면 페이지를 새로 열어 앞사람의 화면과 데이터를 지운다.
 *
 * 다른 파트에서 쓰는 것 (window.Auth):
 *   Auth.client              Supabase 클라이언트. 로그인 사용자 권한(RLS)으로 DB 조회
 *   Auth.user                로그인한 사용자 { id, email } 또는 null
 *   Auth.onReady(fn)         로그인 확인이 끝나면 fn(user) 실행
 *   await Auth.consumeQuota() 분석 실행 직전에 호출. 오늘 한도 안이면 true
 *   await Auth.getProfile()  { plan, daily_usage }
 *   await Auth.refreshAccount() 요금제·사용 횟수 표시 갱신
 *   await Auth.signOut()
 *
 * 화면을 숨기는 것은 1차 방어일 뿐이다. 실제 데이터 보호는 Supabase RLS 정책이 한다.
 */
(() => {
  const cfg = window.SUPABASE_CONFIG;
  if (!window.supabase || !cfg || !cfg.url || !cfg.key || cfg.key.includes("xxxx")) {
    console.error("[auth] supabase-js 또는 part2/config.js 설정이 없습니다.");
    document.addEventListener("DOMContentLoaded", () =>
      showFatal("로그인 설정이 없습니다. part2/config.js를 확인해 주세요.")
    );
    return;
  }

  const client = window.supabase.createClient(cfg.url, cfg.key);
  const MIN_PASSWORD = 6;
  const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

  // Supabase 오류 코드 → 안내 문구
  const MESSAGES = {
    invalid_credentials: "이메일 또는 비밀번호가 올바르지 않습니다.",
    email_not_confirmed: "이메일 인증이 아직 완료되지 않았습니다. 받은 메일의 링크를 눌러 주세요.",
    user_already_exists: "이미 가입된 이메일입니다. 로그인해 주세요.",
    email_exists: "이미 가입된 이메일입니다. 로그인해 주세요.",
    weak_password: `비밀번호가 너무 약합니다. ${MIN_PASSWORD}자 이상으로 입력해 주세요.`,
    email_address_invalid: "사용할 수 없는 이메일 주소입니다.",
    over_email_send_rate_limit: "인증 메일 발송 한도를 넘었습니다. 잠시 후 다시 시도해 주세요.",
    over_request_rate_limit: "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
    signup_disabled: "현재 회원가입이 비활성화되어 있습니다.",
  };
  const NETWORK_ERROR = "로그인 서버에 연결할 수 없습니다. 인터넷 연결을 확인하거나 잠시 후 다시 시도해 주세요.";
  const DEFAULT_ERROR = "처리 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.";

  function messageFor(error) {
    if (!error) return DEFAULT_ERROR;
    if (error.code && MESSAGES[error.code]) return MESSAGES[error.code];
    if (error.name === "AuthRetryableFetchError" || error.status === 0 || error instanceof TypeError) return NETWORK_ERROR;
    return DEFAULT_ERROR;
  }

  function validate(email, password) {
    if (!email || !password) return "이메일과 비밀번호를 모두 입력해 주세요.";
    if (!EMAIL_RE.test(email)) return "이메일 형식이 올바르지 않습니다.";
    if (password.length < MIN_PASSWORD) return `비밀번호는 ${MIN_PASSWORD}자 이상이어야 합니다.`;
    return null;
  }

  // ---------------------------------------------------------------
  // 화면
  // ---------------------------------------------------------------
  let gate = null;
  let accountBar = null;

  function el(tag, attrs = {}, text) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function showFatal(message) {
    document.body.classList.add("auth-locked");
    const box = el("div", { class: "auth-gate", role: "alert" });
    box.append(el("div", { class: "auth-card" }));
    box.firstChild.append(el("p", { class: "auth-msg auth-msg-error" }, message));
    document.body.append(box);
  }

  function buildGate() {
    gate = el("div", { class: "auth-gate", id: "auth-gate" });
    gate.innerHTML = `
      <div class="auth-card" role="dialog" aria-labelledby="auth-title">
        <p class="auth-eyebrow">매출분석 툴</p>
        <h1 id="auth-title">로그인</h1>
        <div class="auth-tabs" role="tablist">
          <button type="button" role="tab" data-tab="login" aria-selected="true">로그인</button>
          <button type="button" role="tab" data-tab="signup" aria-selected="false">회원가입</button>
        </div>
        <form id="auth-login" novalidate>
          <label>이메일<input name="email" type="email" autocomplete="email"></label>
          <label>비밀번호<input name="password" type="password" autocomplete="current-password"></label>
          <button type="submit" class="auth-primary">로그인</button>
        </form>
        <form id="auth-signup" novalidate hidden>
          <label>이메일<input name="email" type="email" autocomplete="email"></label>
          <label>비밀번호 (${MIN_PASSWORD}자 이상)<input name="password" type="password" autocomplete="new-password"></label>
          <label>비밀번호 확인<input name="confirm" type="password" autocomplete="new-password"></label>
          <button type="submit" class="auth-primary">회원가입</button>
        </form>
        <p class="auth-msg" id="auth-msg" aria-live="polite"></p>
      </div>`;
    document.body.append(gate);

    const tabs = gate.querySelectorAll("[data-tab]");
    const forms = { login: gate.querySelector("#auth-login"), signup: gate.querySelector("#auth-signup") };
    tabs.forEach((tab) =>
      tab.addEventListener("click", () => {
        tabs.forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
        for (const [name, form] of Object.entries(forms)) form.hidden = name !== tab.dataset.tab;
        gate.querySelector("#auth-title").textContent = tab.textContent;
        setMessage("");
      })
    );

    forms.login.addEventListener("submit", (e) => {
      e.preventDefault();
      const f = new FormData(forms.login);
      submit(forms.login, () => signIn(String(f.get("email")), String(f.get("password"))));
    });
    forms.signup.addEventListener("submit", (e) => {
      e.preventDefault();
      const f = new FormData(forms.signup);
      submit(forms.signup, () => signUp(String(f.get("email")), String(f.get("password")), String(f.get("confirm"))));
    });
  }

  function setMessage(text, kind = "error") {
    const msg = gate && gate.querySelector("#auth-msg");
    if (!msg) return;
    msg.textContent = text;
    msg.className = `auth-msg auth-msg-${kind}`;
  }

  async function submit(form, action) {
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    setMessage("처리 중...", "info");
    try {
      const result = await action();
      setMessage(result.message, result.ok ? "success" : "error");
    } catch (err) {
      setMessage(messageFor(err));
    } finally {
      button.disabled = false;
    }
  }

  function showGate() {
    document.body.classList.add("auth-locked");
    if (!gate) buildGate();
    gate.hidden = false;
    if (accountBar) accountBar.hidden = true;
    const first = gate.querySelector("form:not([hidden]) input");
    if (first) first.focus();
  }

  async function showApp(user) {
    document.body.classList.remove("auth-locked");
    if (gate) {
      gate.hidden = true;
      gate.querySelectorAll("form").forEach((f) => f.reset());
      setMessage("");
    }
    if (!accountBar) {
      accountBar = el("div", { class: "auth-account", id: "auth-account" });
      accountBar.innerHTML = `<span class="auth-email"></span><span class="auth-plan"></span><button type="button" class="auth-logout">로그아웃</button>`;
      accountBar.querySelector(".auth-logout").addEventListener("click", () => Auth.signOut());
      document.body.append(accountBar);
    }
    accountBar.hidden = false;
    accountBar.querySelector(".auth-email").textContent = user.email;
    const profile = await Auth.getProfile().catch(() => null);
    accountBar.querySelector(".auth-plan").textContent = profile
      ? `${profile.plan === "pro" ? "프로" : "무료"} · 오늘 ${profile.daily_usage}회`
      : "";
  }

  // ---------------------------------------------------------------
  // 로그인 동작
  // ---------------------------------------------------------------
  async function signIn(email, password) {
    email = email.trim().toLowerCase();
    const problem = validate(email, password);
    if (problem) return { ok: false, message: problem };
    const { error } = await client.auth.signInWithPassword({ email, password });
    if (error) return { ok: false, message: messageFor(error) };
    return { ok: true, message: "로그인되었습니다." };
  }

  async function signUp(email, password, confirm) {
    email = email.trim().toLowerCase();
    const problem = validate(email, password);
    if (problem) return { ok: false, message: problem };
    if (password !== confirm) return { ok: false, message: "비밀번호 확인이 일치하지 않습니다." };
    const { data, error } = await client.auth.signUp({ email, password });
    if (error) return { ok: false, message: messageFor(error) };
    // Supabase에서 Confirm email이 켜져 있으면 세션 없이 사용자만 만들어진다
    if (!data.session) return { ok: true, message: "가입 확인 메일을 보냈습니다. 메일의 링크를 누른 뒤 로그인해 주세요." };
    return { ok: true, message: "가입이 완료되었습니다." };
  }

  // ---------------------------------------------------------------
  // 공개 API
  // ---------------------------------------------------------------
  const readyCallbacks = [];
  let ready = false;

  const Auth = {
    client,
    user: null,

    onReady(fn) {
      if (ready && Auth.user) fn(Auth.user);
      else readyCallbacks.push(fn);
    },

    async getProfile() {
      if (!Auth.user) return null;
      const { data, error } = await client
        .from("profiles")
        .select("plan, daily_usage, usage_date")
        .eq("id", Auth.user.id)
        .maybeSingle();
      if (error) throw error;
      return data;
    },

    async consumeQuota() {
      if (!Auth.user) return false;
      const { data, error } = await client.rpc("consume_analysis_quota");
      if (error) throw error;
      if (accountBar) showApp(Auth.user); // 사용 횟수 표시 갱신
      return data === true;
    },

    async refreshAccount() {
      // 결제 등으로 요금제가 바뀐 뒤 계정 표시를 다시 그린다
      if (Auth.user && accountBar) await showApp(Auth.user);
    },

    async signOut() {
      // 서버 쪽 로그아웃이 실패해도 이 브라우저의 로그인 정보는 지운다
      await client.auth.signOut().catch(() => client.auth.signOut({ scope: "local" }));
    },
  };
  window.Auth = Auth;

  function applySession(session) {
    const user = session ? { id: session.user.id, email: session.user.email } : null;
    const previous = Auth.user;
    // 로그인돼 있던 사람이 로그아웃되거나(다른 탭 포함) 다른 계정으로 바뀌면 페이지를 새로 연다.
    // 그래야 앞사람이 불러온 CSV · 계산 결과 · AI 답변이 화면과 메모리에 남지 않는다.
    // 처음 열 때(previous 없음)는 새로고침하지 않는다. 하면 끝없이 다시 불러온다.
    if (previous && (!user || user.id !== previous.id)) {
      Auth.user = null;
      document.body.classList.add("auth-locked"); // 새로고침되기 전 잠깐도 보이지 않게
      location.reload();
      return;
    }
    const changed = (previous && previous.id) !== (user && user.id);
    Auth.user = user;
    if (!user) {
      showGate();
      return;
    }
    if (changed || !ready) showApp(user);
    if (!ready || changed) {
      ready = true;
      readyCallbacks.splice(0).forEach((fn) => fn(user));
    }
  }

  function start() {
    // 로그인 · 로그아웃 · 다른 탭에서의 로그아웃까지 모두 여기로 들어온다
    client.auth.onAuthStateChange((_event, session) => {
      // 콜백 안에서 Supabase 호출을 바로 하면 멈출 수 있어 다음 틱으로 미룬다
      setTimeout(() => applySession(session), 0);
    });
  }

  if (document.body) document.body.classList.add("auth-locked"); // 확인 전에 원래 화면이 잠깐 보이지 않게
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => { document.body.classList.add("auth-locked"); start(); });
  else start();
})();
