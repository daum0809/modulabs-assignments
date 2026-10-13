-- =====================================================================
-- 결제 처리 함수 (schema.sql 실행 후, SQL Editor에서 실행. 여러 번 실행해도 안전)
--
--   create_payment_order : 로그인 사용자가 호출. 금액은 plans 표에서만 가져옴
--   complete_payment     : 서버(service_role)만 호출. 토스 승인 성공 후 요금제 변경
--   fail_payment         : 서버(service_role)만 호출. 결제 실패·취소 기록
-- =====================================================================


-- 주문 생성: 사용자는 요금제 코드만 고르고, 금액은 DB가 정한다
create or replace function public.create_payment_order(p_plan text)
returns json
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid   uuid := auth.uid();
  v_price integer;
  v_name  text;
  v_order text;
begin
  if v_uid is null then
    raise exception 'not authenticated';
  end if;

  -- 이미 같은 요금제를 쓰는 사용자는 다시 결제할 수 없다
  if exists (select 1 from public.profiles p where p.id = v_uid and p.plan = p_plan) then
    raise exception 'already on plan: %', p_plan;
  end if;

  select pl.price, pl.name into v_price, v_name
    from public.plans pl
   where pl.code = p_plan;

  if v_price is null or v_price <= 0 then
    raise exception 'invalid plan: %', p_plan;
  end if;

  -- 토스 orderId 규칙: 6~64자, 영문·숫자·-·_
  v_order := 'ORD-' || replace(gen_random_uuid()::text, '-', '');

  insert into public.payments (order_id, user_id, plan, amount)
  values (v_order, v_uid, p_plan, v_price);

  return json_build_object(
    'order_id',   v_order,
    'amount',     v_price,
    'order_name', '매출분석 툴 ' || v_name || ' 플랜'
  );
end;
$$;

revoke execute on function public.create_payment_order(text) from public, anon;
grant  execute on function public.create_payment_order(text) to authenticated;


-- 결제 완료: 대기 중인 주문만 완료 처리 → 같은 주문의 중복 처리 방지
create or replace function public.complete_payment(p_order_id text, p_payment_key text)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user uuid;
  v_plan text;
begin
  update public.payments
     set status = 'done',
         payment_key = p_payment_key,
         approved_at = now()
   where order_id = p_order_id
     and status = 'pending'
  returning user_id, plan into v_user, v_plan;

  if v_user is null then
    return false;
  end if;

  update public.profiles set plan = v_plan where id = v_user;
  return true;
end;
$$;

revoke execute on function public.complete_payment(text, text) from public, anon, authenticated;
grant  execute on function public.complete_payment(text, text) to service_role;


-- 결제 실패·취소 기록: 대기 중인 주문만
create or replace function public.fail_payment(p_order_id text, p_reason text)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.payments
     set status = case when p_reason = 'PAY_PROCESS_CANCELED' then 'cancelled' else 'failed' end,
         fail_reason = left(p_reason, 200)
   where order_id = p_order_id
     and status = 'pending';
  return found;
end;
$$;

revoke execute on function public.fail_payment(text, text) from public, anon, authenticated;
grant  execute on function public.fail_payment(text, text) to service_role;
