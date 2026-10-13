-- =====================================================================
-- M1팀 쇼핑몰 매출 분석 에이전트: Supabase 스키마 + RLS 정책
-- 실행 위치: Supabase 대시보드 > SQL Editor (한 번에 전체 실행)
--
-- 권한 원칙
--   - 모든 테이블에 RLS를 켜고, 로그인 사용자(authenticated)는 "자기 데이터"만 접근
--   - 비로그인(anon)에게는 plans(요금제 목록) 조회만 허용
--   - plan 변경, 결제 기록은 사용자가 직접 못 바꿈 → Streamlit 서버가 service_role 키로 처리
--   - dataset_versions, tool_steps는 수정 불가(추가만) → 재현성 보장
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. 요금제 (결제 금액의 기준값. 금액 검증은 항상 이 테이블 기준)
-- ---------------------------------------------------------------------
create table public.plans (
  code        text primary key,               -- 'free', 'pro'
  name        text not null,
  price       integer not null check (price >= 0),   -- 원 단위
  daily_limit integer check (daily_limit > 0)        -- 하루 질문 한도, null = 무제한
);

insert into public.plans (code, name, price, daily_limit) values
  ('free', '무료', 0, 5),
  ('pro',  '프로', 9900, null);


-- ---------------------------------------------------------------------
-- 2. 사용자 프로필 (auth.users 가입 시 자동 생성)
-- ---------------------------------------------------------------------
create table public.profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  email       text,
  plan        text not null default 'free' references public.plans (code),
  daily_usage integer not null default 0 check (daily_usage >= 0),
  usage_date  date not null default ((now() at time zone 'Asia/Seoul')::date),
  created_at  timestamptz not null default now()
);

-- 회원가입 시 profiles 행 자동 생성
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, email) values (new.id, new.email);
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();


-- ---------------------------------------------------------------------
-- 3. 프로젝트 (운영자별 분석 공간)
-- ---------------------------------------------------------------------
create table public.projects (
  id         uuid primary key default gen_random_uuid(),
  owner_id   uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  name       text not null check (char_length(name) between 1 and 100),
  created_at timestamptz not null default now()
);
create index on public.projects (owner_id);


-- ---------------------------------------------------------------------
-- 4. 데이터셋 (업로드한 원본 CSV. 원본은 수정하지 않음)
-- ---------------------------------------------------------------------
create table public.datasets (
  id                uuid primary key default gen_random_uuid(),
  project_id        uuid not null references public.projects (id) on delete cascade,
  original_filename text not null,
  storage_path      text not null,             -- Storage 'datasets' 버킷 내 경로: {user_id}/...
  size_bytes        integer check (size_bytes >= 0),
  created_at        timestamptz not null default now()
);
create index on public.datasets (project_id);


-- ---------------------------------------------------------------------
-- 5. 데이터 버전 (전처리 결과. 한 번 만들면 수정 불가)
--    version_no = 1 : 원본 그대로 / 2 이상 : 결측·중복 처리 등 변환본
-- ---------------------------------------------------------------------
create table public.dataset_versions (
  id            uuid primary key default gen_random_uuid(),
  dataset_id    uuid not null references public.datasets (id) on delete cascade,
  version_no    integer not null check (version_no >= 1),
  storage_path  text not null,
  row_count     integer not null check (row_count >= 0),
  preprocessing jsonb not null default '{}'::jsonb,  -- 예: {"missing":"drop_rows","dropped_rows":2}
  created_at    timestamptz not null default now(),
  unique (dataset_id, version_no)
);
create index on public.dataset_versions (dataset_id);


-- ---------------------------------------------------------------------
-- 6. 분석 실행 (질문 → 계획 → 승인 → 결과)
-- ---------------------------------------------------------------------
create table public.analysis_runs (
  id                 uuid primary key default gen_random_uuid(),
  project_id         uuid not null references public.projects (id) on delete cascade,
  dataset_version_id uuid not null references public.dataset_versions (id) on delete cascade,
  question           text not null check (char_length(question) <= 1000),
  plan               jsonb,                    -- LLM이 만든 분석 요청(JSON), 서버 검증 후 저장
  status             text not null default 'planned'
                     check (status in ('planned', 'approved', 'running', 'succeeded', 'failed', 'cancelled')),
  result             jsonb,                    -- 계산 엔진 결과(표 데이터)
  error              text,
  created_at         timestamptz not null default now(),
  approved_at        timestamptz,
  finished_at        timestamptz
);
create index on public.analysis_runs (project_id);
create index on public.analysis_runs (dataset_version_id);


-- ---------------------------------------------------------------------
-- 7. 실행 단계 기록 (도구 실행 로그. 추가만 가능)
-- ---------------------------------------------------------------------
create table public.tool_steps (
  id            uuid primary key default gen_random_uuid(),
  run_id        uuid not null references public.analysis_runs (id) on delete cascade,
  step_no       integer not null check (step_no >= 1),
  tool          text not null,                 -- 예: 'filter_period', 'group_sum', 'compare_periods'
  input_summary jsonb not null default '{}'::jsonb,
  output        jsonb,
  status        text not null check (status in ('succeeded', 'failed', 'cancelled')),
  error         text,
  started_at    timestamptz,
  finished_at   timestamptz,
  unique (run_id, step_no)
);
create index on public.tool_steps (run_id);


-- ---------------------------------------------------------------------
-- 8. 결제 (토스페이먼츠 테스트 모드)
--    생성·승인 모두 Streamlit 서버가 service_role 키로 처리. 사용자는 조회만.
-- ---------------------------------------------------------------------
create table public.payments (
  id          uuid primary key default gen_random_uuid(),
  order_id    text not null unique,            -- 중복 승인 방지
  user_id     uuid not null references public.profiles (id) on delete cascade,
  plan        text not null references public.plans (code),
  amount      integer not null check (amount > 0),   -- 주문 생성 시 plans.price에서 복사
  status      text not null default 'pending'
              check (status in ('pending', 'done', 'failed', 'cancelled')),
  payment_key text unique,
  fail_reason text,
  created_at  timestamptz not null default now(),
  approved_at timestamptz
);
create index on public.payments (user_id);


-- =====================================================================
-- RLS 정책
-- (select auth.uid()) 형태는 행마다 함수를 다시 부르지 않게 하는 Supabase 권장 방식
-- =====================================================================

alter table public.plans            enable row level security;
alter table public.profiles         enable row level security;
alter table public.projects         enable row level security;
alter table public.datasets         enable row level security;
alter table public.dataset_versions enable row level security;
alter table public.analysis_runs    enable row level security;
alter table public.tool_steps       enable row level security;
alter table public.payments         enable row level security;


-- plans: 누구나 조회만
create policy "plans_select_all" on public.plans
  for select to anon, authenticated using (true);


-- profiles: 본인 조회만. 수정 정책 없음 → 사용자가 plan을 'pro'로 바꾸는 것 차단
create policy "profiles_select_own" on public.profiles
  for select to authenticated
  using (id = (select auth.uid()));


-- projects: 본인 소유만 조회·생성·수정·삭제
create policy "projects_select_own" on public.projects
  for select to authenticated
  using (owner_id = (select auth.uid()));

create policy "projects_insert_own" on public.projects
  for insert to authenticated
  with check (owner_id = (select auth.uid()));

create policy "projects_update_own" on public.projects
  for update to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy "projects_delete_own" on public.projects
  for delete to authenticated
  using (owner_id = (select auth.uid()));


-- datasets: 내 프로젝트에 속한 것만
create policy "datasets_select_own" on public.datasets
  for select to authenticated
  using (exists (
    select 1 from public.projects p
    where p.id = project_id and p.owner_id = (select auth.uid())
  ));

create policy "datasets_insert_own" on public.datasets
  for insert to authenticated
  with check (exists (
    select 1 from public.projects p
    where p.id = project_id and p.owner_id = (select auth.uid())
  ));

create policy "datasets_delete_own" on public.datasets
  for delete to authenticated
  using (exists (
    select 1 from public.projects p
    where p.id = project_id and p.owner_id = (select auth.uid())
  ));


-- dataset_versions: 조회·추가만 (수정 정책 없음 → 버전 고정)
create policy "versions_select_own" on public.dataset_versions
  for select to authenticated
  using (exists (
    select 1 from public.datasets d
    join public.projects p on p.id = d.project_id
    where d.id = dataset_id and p.owner_id = (select auth.uid())
  ));

create policy "versions_insert_own" on public.dataset_versions
  for insert to authenticated
  with check (exists (
    select 1 from public.datasets d
    join public.projects p on p.id = d.project_id
    where d.id = dataset_id and p.owner_id = (select auth.uid())
  ));


-- analysis_runs: 내 프로젝트 + "같은 프로젝트의 데이터 버전"만 연결 가능
-- (외래키 검사는 RLS를 무시하므로, 남의 버전 ID를 넣는 것을 여기서 막음)
create policy "runs_select_own" on public.analysis_runs
  for select to authenticated
  using (exists (
    select 1 from public.projects p
    where p.id = project_id and p.owner_id = (select auth.uid())
  ));

create policy "runs_insert_own" on public.analysis_runs
  for insert to authenticated
  with check (exists (
    select 1 from public.dataset_versions v
    join public.datasets d on d.id = v.dataset_id
    join public.projects p on p.id = d.project_id
    where v.id = analysis_runs.dataset_version_id
      and d.project_id = analysis_runs.project_id
      and p.owner_id = (select auth.uid())
  ));

create policy "runs_update_own" on public.analysis_runs
  for update to authenticated
  using (exists (
    select 1 from public.projects p
    where p.id = project_id and p.owner_id = (select auth.uid())
  ))
  with check (exists (
    select 1 from public.dataset_versions v
    join public.datasets d on d.id = v.dataset_id
    join public.projects p on p.id = d.project_id
    where v.id = analysis_runs.dataset_version_id
      and d.project_id = analysis_runs.project_id
      and p.owner_id = (select auth.uid())
  ));

create policy "runs_delete_own" on public.analysis_runs
  for delete to authenticated
  using (exists (
    select 1 from public.projects p
    where p.id = project_id and p.owner_id = (select auth.uid())
  ));


-- tool_steps: 조회·추가만 (실행 기록은 사후 수정 불가)
create policy "steps_select_own" on public.tool_steps
  for select to authenticated
  using (exists (
    select 1 from public.analysis_runs r
    join public.projects p on p.id = r.project_id
    where r.id = run_id and p.owner_id = (select auth.uid())
  ));

create policy "steps_insert_own" on public.tool_steps
  for insert to authenticated
  with check (exists (
    select 1 from public.analysis_runs r
    join public.projects p on p.id = r.project_id
    where r.id = run_id and p.owner_id = (select auth.uid())
  ));


-- payments: 본인 결제 내역 조회만 (생성·승인은 서버의 service_role 키로만)
create policy "payments_select_own" on public.payments
  for select to authenticated
  using (user_id = (select auth.uid()));


-- =====================================================================
-- 사용량 한도 함수: 분석 실행 직전에 호출
--   한도 안이면 사용량 +1 하고 true, 초과면 false
--   날짜가 바뀌면(한국 시간 기준) 0부터 다시 셈
-- =====================================================================
create or replace function public.consume_analysis_quota()
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid   uuid := auth.uid();
  v_today date := (now() at time zone 'Asia/Seoul')::date;
  v_ok    boolean;
begin
  if v_uid is null then
    raise exception 'not authenticated';
  end if;

  update public.profiles p
     set daily_usage = case when p.usage_date < v_today then 1 else p.daily_usage + 1 end,
         usage_date  = v_today
   where p.id = v_uid
     and (
       p.usage_date < v_today
       or p.daily_usage < coalesce(
            (select pl.daily_limit from public.plans pl where pl.code = p.plan),
            2147483647)
     )
  returning true into v_ok;

  return coalesce(v_ok, false);
end;
$$;

revoke execute on function public.consume_analysis_quota() from public, anon;
grant  execute on function public.consume_analysis_quota() to authenticated;


-- =====================================================================
-- Storage: CSV 파일 버킷 (비공개, 5MB 제한)
--   파일 경로 규칙: {user_id}/{project_id}/{파일명}
--   → 첫 폴더가 본인 user_id인 파일만 읽기·올리기·삭제 가능
-- =====================================================================
insert into storage.buckets (id, name, public, file_size_limit)
values ('datasets', 'datasets', false, 5242880);

create policy "datasets_files_select_own" on storage.objects
  for select to authenticated
  using (bucket_id = 'datasets'
         and (storage.foldername(name))[1] = (select auth.uid())::text);

create policy "datasets_files_insert_own" on storage.objects
  for insert to authenticated
  with check (bucket_id = 'datasets'
              and (storage.foldername(name))[1] = (select auth.uid())::text);

create policy "datasets_files_delete_own" on storage.objects
  for delete to authenticated
  using (bucket_id = 'datasets'
         and (storage.foldername(name))[1] = (select auth.uid())::text);
