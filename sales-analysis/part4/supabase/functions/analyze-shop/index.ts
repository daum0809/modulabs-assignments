import { createClient } from "jsr:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS"
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const authHeader = req.headers.get("Authorization") ?? "";
    if (!authHeader.startsWith("Bearer ")) {
      return new Response(JSON.stringify({ error: "로그인이 필요합니다." }), {
        status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    const supa = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_ANON_KEY")!,
      { global: { headers: { Authorization: authHeader } } }
    );

    const { data: { user }, error: userError } = await supa.auth.getUser();
    if (userError || !user) {
      return new Response(JSON.stringify({ error: "로그인이 필요합니다." }), {
        status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    const { data: allowed, error: quotaError } = await supa.rpc("consume_analysis_quota");
    if (quotaError) {
      return new Response(JSON.stringify({ error: "사용 한도 확인에 실패했습니다." }), {
        status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }
    if (!allowed) {
      return new Response(JSON.stringify({ error: "오늘의 무료 분석 5회를 모두 사용했습니다." }), {
        status: 429, headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    const body = await req.json();
    const result = body.result;
    const question = body.question || "핵심 문제와 다음 액션을 분석해줘.";
    if (!result?.current) throw new Error("Calculated KPI result is required.");

    const apiKey = Deno.env.get("OPENAI_API_KEY");
    if (!apiKey) throw new Error("Server secret OPENAI_API_KEY is missing.");

    const instructions = [
      "당신은 쇼핑몰 데이터 분석가입니다.",
      "제공된 KPI와 diagnostics를 다시 계산하지 마세요.",
      "확인된 사실과 원인 후보를 구분하세요.",
      "경쟁가격 관측을 검토하되 인과관계를 단정하지 마세요.",
      "다음 액션은 우선순위 순 최대 3개로 제시하세요.",
      "한국어로 간결하게 답하세요."
    ].join("\n");

    const input = instructions + "\n\n사용자 질문: " + question +
      "\n\n계산 완료 데이터:\n" + JSON.stringify(result);

    const response = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: { "Authorization": "Bearer " + apiKey, "Content-Type": "application/json" },
      body: JSON.stringify({ model: "gpt-5.6", input })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const reason = data?.error?.message ?? response.statusText;
      console.error("OpenAI error", response.status, data?.error?.code ?? "", reason);
      throw new Error(`OpenAI request failed (${response.status}): ${reason}`);
    }

    const analysis = data.output_text ??
      data.output?.flatMap((x) => x.content ?? []).find((x) => x.type === "output_text")?.text ?? "";

    return new Response(JSON.stringify({ analysis }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" }
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: error instanceof Error ? error.message : String(error) }), {
      status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" }
    });
  }
});