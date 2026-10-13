// [담당2] 토스페이먼츠 결제 승인 Edge Function (테스트 모드)
//
// 브라우저가 로그인 토큰과 함께 호출한다: Auth.client.functions.invoke("confirm-payment", { body })
//   { action: "confirm", paymentKey, orderId, amount }  토스 successUrl로 돌아온 값
//   { action: "fail", orderId, code }                   토스 failUrl로 돌아왔거나 결제창을 닫은 경우
//
// 검사 순서: 로그인 사용자 확인 → 주문의 주인 확인 → 주문 상태 확인 → DB 금액과 대조 → 이미 같은 요금제인지 → 토스 승인 → 요금제 변경
// 필요한 Secret: TOSS_SECRET_KEY (test_sk_...). SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY는 Supabase가 자동으로 넣어 준다.

import { createClient } from "jsr:@supabase/supabase-js@2";

// 결제 페이지 주소 (배포 주소가 바뀌면 여기에 추가)
const ALLOWED_ORIGINS = ["https://ctaleez51-art.github.io", "http://localhost:8510"];
const TOSS_CONFIRM_URL = "https://api.tosspayments.com/v1/payments/confirm";

function corsHeaders(origin: string | null): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": origin && ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0],
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Vary": "Origin",
  };
}

Deno.serve(async (req) => {
  const headers = { ...corsHeaders(req.headers.get("Origin")), "Content-Type": "application/json" };
  const reply = (status: number, body: Record<string, unknown>) =>
    new Response(JSON.stringify(body), { status, headers });

  if (req.method === "OPTIONS") return new Response("ok", { headers });
  if (req.method !== "POST") return reply(405, { ok: false, message: "허용되지 않은 요청입니다." });

  // 실제 결제 키로는 동작하지 않게 막는다
  const secret = Deno.env.get("TOSS_SECRET_KEY") ?? "";
  if (!secret.startsWith("test_sk_")) {
    return reply(500, { ok: false, message: "결제 서버 설정 오류: 토스 테스트 시크릿 키(test_sk_)가 필요합니다." });
  }

  const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

  // 1) 로그인 사용자 확인
  const jwt = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "");
  const { data: userData, error: userError } = await admin.auth.getUser(jwt);
  const user = userData?.user;
  if (userError || !user) return reply(401, { ok: false, message: "로그인이 필요합니다." });

  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return reply(400, { ok: false, message: "요청 형식이 올바르지 않습니다." });
  }
  const action = body.action ?? "confirm";
  const orderId = typeof body.orderId === "string" ? body.orderId : "";
  const paymentKey = typeof body.paymentKey === "string" ? body.paymentKey : "";
  if (!orderId) return reply(400, { ok: false, message: "주문 번호가 없습니다." });

  // 2) 주문의 주인 확인 (다른 사람 주문이면 없는 주문처럼 응답)
  const { data: order, error: orderError } = await admin
    .from("payments")
    .select("order_id, user_id, plan, amount, status, payment_key")
    .eq("order_id", orderId)
    .maybeSingle();
  if (orderError) return reply(500, { ok: false, message: "주문을 조회하지 못했습니다." });
  if (!order || order.user_id !== user.id) return reply(404, { ok: false, message: "주문을 찾을 수 없습니다." });

  const fail = (reason: string) => admin.rpc("fail_payment", { p_order_id: orderId, p_reason: reason });

  if (action === "fail") {
    await fail(String(body.code ?? "UNKNOWN").slice(0, 100));
    return reply(200, { ok: true, message: "결제 실패를 기록했습니다." });
  }

  // 3) 주문 상태 확인: 새로고침 등으로 다시 호출돼도 두 번 승인하지 않는다
  if (order.status === "done") {
    return order.payment_key === paymentKey
      ? reply(200, { ok: true, already: true, message: "이미 처리된 결제입니다. 프로 플랜이 적용되어 있습니다." })
      : reply(409, { ok: false, message: "이미 다른 결제로 처리된 주문입니다." });
  }
  if (order.status !== "pending") return reply(409, { ok: false, message: "결제할 수 없는 주문 상태입니다." });
  if (!paymentKey) return reply(400, { ok: false, message: "결제 정보가 없습니다." });

  // 4) 금액 검증: 돌아온 값이 아니라 DB에 저장한 금액이 기준
  if (Number(body.amount) !== order.amount) {
    await fail("AMOUNT_MISMATCH");
    return reply(400, { ok: false, message: "결제 금액이 주문 금액과 달라 승인하지 않았습니다." });
  }

  // 이미 같은 요금제면 승인하지 않는다 (다른 탭에서 먼저 결제한 경우). 승인 안 된 결제는 청구되지 않는다
  const { data: profile } = await admin.from("profiles").select("plan").eq("id", user.id).maybeSingle();
  if (profile?.plan === order.plan) {
    await fail("ALREADY_ON_PLAN");
    return reply(409, { ok: false, message: "이미 프로 플랜을 쓰고 있어 결제를 승인하지 않았습니다. 청구되지 않습니다." });
  }

  // 5) 토스 승인 API
  let res: Response;
  try {
    res = await fetch(TOSS_CONFIRM_URL, {
      method: "POST",
      headers: { Authorization: "Basic " + btoa(secret + ":"), "Content-Type": "application/json" },
      body: JSON.stringify({ paymentKey, orderId, amount: order.amount }),
    });
  } catch {
    // 승인 여부를 알 수 없으므로 실패로 기록하지 않는다 (다시 호출하면 재시도됨)
    return reply(502, { ok: false, message: "결제 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요." });
  }
  const toss = await res.json().catch(() => ({}));
  if (!res.ok) {
    await fail(toss.code ?? `HTTP_${res.status}`);
    return reply(400, { ok: false, code: toss.code, message: `결제 승인에 실패했습니다. (${toss.message ?? toss.code ?? res.status})` });
  }

  // 6) 요금제 변경
  const { error: doneError } = await admin.rpc("complete_payment", { p_order_id: orderId, p_payment_key: paymentKey });
  if (doneError) {
    return reply(500, { ok: false, message: "결제는 승인됐지만 요금제 반영에 실패했습니다. 담당자에게 알려 주세요." });
  }
  return reply(200, { ok: true, message: "결제가 완료되었습니다. 프로 플랜이 적용되었습니다." });
});
