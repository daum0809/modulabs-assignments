-- =====================================================================
-- RLS 권한 테스트 (Supabase SQL Editor에서 전체 실행)
--
-- 1) 아래 두 줄의 A_USER_ID, B_USER_ID를 테스트 계정 UID로 바꾸기
--    (Authentication > Users 목록에서 계정 클릭 → User UID 복사)
-- 2) 전체 실행 → 마지막에 결과표(통과/실패)가 한 번에 나옴
-- 3) 테스트가 모두 끝나면 맨 아래 "정리" 주석의 한 줄을 따로 실행
--
-- SQL Editor는 마지막 쿼리 결과만 보여주므로, 각 테스트 결과를
-- testing.rls_results 표에 모아 두었다가 마지막에 출력함
-- =====================================================================

reset role;

-- ▼▼▼ 이 두 줄만 바꾸기 ▼▼▼
select set_config('test.a_uid', 'A_USER_ID', false);
select set_config('test.b_uid', 'B_USER_ID', false);
-- ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

-- 결과 기록용 표 (API에 노출되지 않는 별도 스키마)
create schema if not exists testing;
drop table if exists testing.rls_results;
create table testing.rls_results (no int, test text, expected text, actual text);
grant usage on schema testing to authenticated, anon;
grant select, insert on testing.rls_results to authenticated, anon;

-- 이전 실행에서 남은 테스트 데이터 정리
delete from public.projects where name in ('RLS테스트_A프로젝트', '탈취', 'RLS테스트_위장');
update public.profiles set daily_usage = 0 where id = current_setting('test.b_uid')::uuid;


-- ---------------------------------------------------------------
-- [운영자 A로 로그인한 상태]
-- ---------------------------------------------------------------
select set_config('request.jwt.claims',
  json_build_object('sub', current_setting('test.a_uid'), 'role', 'authenticated')::text, false);
set role authenticated;

insert into public.projects (name) values ('RLS테스트_A프로젝트');

insert into testing.rls_results
select 1, 'A: 내 프로젝트 조회', '1',
       (select count(*) from public.projects where name = 'RLS테스트_A프로젝트')::text;

insert into testing.rls_results
select 2, 'A: 내 프로필 요금제', 'free',
       (select plan from public.profiles where id = current_setting('test.a_uid')::uuid);


-- ---------------------------------------------------------------
-- [운영자 B로 로그인한 상태]
-- ---------------------------------------------------------------
reset role;
select set_config('request.jwt.claims',
  json_build_object('sub', current_setting('test.b_uid'), 'role', 'authenticated')::text, false);
set role authenticated;

-- B는 A의 프로젝트를 볼 수 없어야 함
insert into testing.rls_results
select 3, 'B: A의 프로젝트 조회', '0',
       (select count(*) from public.projects where name = 'RLS테스트_A프로젝트')::text;

-- B는 A의 프로젝트를 수정할 수 없어야 함
with u as (
  update public.projects set name = '탈취'
  where name = 'RLS테스트_A프로젝트' returning 1
)
insert into testing.rls_results
select 4, 'B: A의 프로젝트 이름 변경', '0행 변경', count(*) || '행 변경' from u;

-- B는 A 소유로 프로젝트를 만들 수 없어야 함
do $$
begin
  insert into public.projects (name, owner_id)
  values ('RLS테스트_위장', current_setting('test.a_uid')::uuid);
  insert into testing.rls_results values (5, 'B: A 소유로 프로젝트 생성', '거부', '허용됨');
exception when insufficient_privilege then
  insert into testing.rls_results values (5, 'B: A 소유로 프로젝트 생성', '거부', '거부');
end $$;

-- B는 스스로 프로 플랜으로 바꿀 수 없어야 함
with u as (
  update public.profiles set plan = 'pro'
  where id = current_setting('test.b_uid')::uuid returning 1
)
insert into testing.rls_results
select 6, 'B: 스스로 프로 플랜 변경', '0행 변경', count(*) || '행 변경' from u;

-- B는 결제 기록을 직접 만들 수 없어야 함
do $$
begin
  insert into public.payments (order_id, user_id, plan, amount)
  values ('rls-test-fake-order', current_setting('test.b_uid')::uuid, 'pro', 100);
  insert into testing.rls_results values (7, 'B: 결제 기록 직접 생성', '거부', '허용됨');
exception when insufficient_privilege then
  insert into testing.rls_results values (7, 'B: 결제 기록 직접 생성', '거부', '거부');
end $$;

-- 무료 플랜 하루 5회 한도: 6번 호출하면 마지막만 false(F)
insert into testing.rls_results
select 8, 'B: 무료 한도 6회 호출', 'T,T,T,T,T,F',
       string_agg(case when public.consume_analysis_quota() then 'T' else 'F' end, ',' order by g)
from generate_series(1, 6) as g;


-- ---------------------------------------------------------------
-- [비로그인 상태]
-- ---------------------------------------------------------------
reset role;
select set_config('request.jwt.claims', '{"role":"anon"}', false);
set role anon;

insert into testing.rls_results
select 9, '비로그인: 요금제 조회', '2', (select count(*) from public.plans)::text;

insert into testing.rls_results
select 10, '비로그인: 프로젝트 조회', '0', (select count(*) from public.projects)::text;


-- ---------------------------------------------------------------
-- 테스트 데이터 정리 (관리자 권한으로 복귀)
-- ---------------------------------------------------------------
reset role;
select set_config('request.jwt.claims', '', false);
delete from public.projects where name in ('RLS테스트_A프로젝트', '탈취', 'RLS테스트_위장');
delete from public.payments where order_id = 'rls-test-fake-order';
update public.profiles set daily_usage = 0 where id = current_setting('test.b_uid')::uuid;


-- ---------------------------------------------------------------
-- 결과표 (이 결과가 화면에 나옴)
-- ---------------------------------------------------------------
select no, test, expected, actual,
       case when expected = actual then '✅ 통과' else '❌ 실패' end as result
from testing.rls_results
order by no;


-- 정리: 테스트를 모두 마친 뒤 아래 한 줄만 따로 실행
-- drop schema testing cascade;
