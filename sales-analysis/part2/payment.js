/**
 * [담당2] 프로 플랜 결제 (토스페이먼츠 테스트 모드)
 *
 * 붙이는 법: auth.js 다음에
 *   <script src="https://js.tosspayments.com/v2/standard"></script>
 *   <script src="../part2/payment.js"></script>
 *
 * 무료 사용자에게 오른쪽 위 계정 표시에 [프로 결제] 버튼이 생긴다.
 * 결제 후 같은 페이지로 돌아오면(?pay=success / ?pay=fail) Edge Function "confirm-payment"가
 * 금액을 DB와 대조해 승인하고, 결과를 화면 위쪽 알림으로 보여준다.
 * 금액은 DB(plans 표)에서만 정해지고, 토스 시크릿 키는 Edge Function에만 있다.
 */
(() => {
  if (!window.Auth) return;
  const cfg = window.SUPABASE_CONFIG || {};
  const PLAN = "pro";
  const params = new URLSearchParams(location.search);

  function banner(text, kind = "info") {
    let box = document.getElementById("pay-banner");
    if (!box) {
      box = document.createElement("div");
      box.id = "pay-banner";
      box.setAttribute("role", "status");
      box.innerHTML = `<span></span><button type="button" aria-label="알림 닫기">×</button>`;
      box.querySelector("button").addEventListener("click", () => box.remove());
      document.body.prepend(box);
    }
    box.className = `pay-banner pay-banner-${kind}`;
    box.querySelector("span").textContent = text;
  }

  // Edge Function 호출. 실패 응답(4xx·5xx)의 안내 문구도 꺼내 온다
  async function callServer(body) {
    const { data, error } = await Auth.client.functions.invoke("confirm-payment", { body });
    if (!error) return data;
    try {
      const detail = await error.context.json();
      if (detail && detail.message) return detail;
    } catch (_) { /* 응답 본문이 없는 네트워크 오류 */ }
    return { ok: false, message: "결제 확인 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요." };
  }

  async function startCheckout(button) {
    if (!window.TossPayments) return banner("결제 모듈을 불러오지 못했습니다. 새로고침해 주세요.", "error");
    if (!cfg.tossClientKey || !cfg.tossClientKey.startsWith("test_ck_")) {
      return banner("토스 테스트 클라이언트 키(test_ck_)가 설정되지 않았습니다. part2/config.js를 확인해 주세요.", "error");
    }
    button.disabled = true;
    let order = null;
    try {
      const { data, error } = await Auth.client.rpc("create_payment_order", { p_plan: PLAN });
      if (error) {
        if (String(error.message).includes("already on plan")) {
          await Auth.refreshAccount();
          await renderUpgradeButton();
          return banner("이미 프로 플랜을 쓰고 있어요.", "info");
        }
        throw error;
      }
      order = data;
      const back = location.origin + location.pathname;
      await TossPayments(cfg.tossClientKey)
        .payment({ customerKey: Auth.user.id })
        .requestPayment({
          method: "CARD",
          amount: { currency: "KRW", value: order.amount },
          orderId: order.order_id,
          orderName: order.order_name,
          customerEmail: Auth.user.email,
          successUrl: back + "?pay=success",
          failUrl: back + "?pay=fail",
        });
    } catch (err) {
      // PC에서 결제창을 닫으면 페이지 이동 없이 여기로 온다
      const cancelled = err && err.code === "USER_CANCEL";
      if (order) callServer({ action: "fail", orderId: order.order_id, code: cancelled ? "PAY_PROCESS_CANCELED" : err.code || "CLIENT_ERROR" });
      banner(cancelled ? "결제를 취소했습니다." : "결제를 시작하지 못했습니다. " + ((err && err.message) || ""), cancelled ? "info" : "error");
    } finally {
      button.disabled = false;
    }
  }

  async function renderUpgradeButton() {
    const bar = document.getElementById("auth-account");
    if (!bar) return;
    const profile = await Auth.getProfile().catch(() => null);
    let button = bar.querySelector(".pay-upgrade");
    if (!profile || profile.plan !== "free") {
      if (button) button.remove();
      return;
    }
    if (!button) {
      const { data: plan } = await Auth.client.from("plans").select("price").eq("code", PLAN).maybeSingle();
      button = document.createElement("button");
      button.type = "button";
      button.className = "pay-upgrade";
      button.textContent = plan ? `프로 결제 (${plan.price.toLocaleString("ko-KR")}원)` : "프로 결제";
      button.addEventListener("click", () => startCheckout(button));
      bar.insertBefore(button, bar.querySelector(".auth-logout"));
    }
  }

  // 결제창에서 돌아온 경우: 결과 처리 후 주소창의 결제 값을 지운다
  async function handleReturn() {
    const status = params.get("pay");
    if (status === "success") {
      banner("결제를 확인하는 중...", "info");
      const result = await callServer({
        action: "confirm",
        paymentKey: params.get("paymentKey"),
        orderId: params.get("orderId"),
        amount: params.get("amount"),
      });
      banner(result.message, result.ok ? "success" : "error");
    } else if (status === "fail") {
      const orderId = params.get("orderId");
      if (orderId) await callServer({ action: "fail", orderId, code: params.get("code") });
      banner(`결제가 완료되지 않았습니다. (${params.get("message") || "결제 취소"})`, "info");
    } else {
      return;
    }
    history.replaceState(null, "", location.pathname);
    await Auth.refreshAccount();
  }

  Auth.onReady(async () => {
    await handleReturn();
    await renderUpgradeButton();
  });
})();
