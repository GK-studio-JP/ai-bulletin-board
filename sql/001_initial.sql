-- AI Bulletin Board v0.1 — PostgreSQL / Supabase

create extension if not exists pgcrypto;

create table if not exists public.ai_agents (
  agent_id text primary key,
  display_name text,
  capabilities text[] not null default '{}',
  metadata jsonb not null default '{}'::jsonb,
  last_seen_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.ai_tasks (
  task_id uuid primary key default gen_random_uuid(),
  parent_task_id uuid references public.ai_tasks(task_id),
  title text not null,
  objective text not null,
  acceptance_criteria jsonb not null default '[]'::jsonb,
  status text not null default 'open' check (status in ('open','claimed','working','handoff','blocked','done','cancelled')),
  priority text not null default 'normal' check (priority in ('low','normal','high','critical')),
  capabilities text[] not null default '{}',
  depends_on uuid[] not null default '{}',
  claimed_by text references public.ai_agents(agent_id),
  lease_expires_at timestamptz,
  context jsonb not null default '{}'::jsonb,
  artifacts jsonb not null default '[]'::jsonb,
  next_action text,
  blocked_reason text,
  version bigint not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.ai_task_events (
  event_id uuid primary key default gen_random_uuid(),
  task_id uuid not null references public.ai_tasks(task_id) on delete cascade,
  event_type text not null check (event_type in ('created','claimed','heartbeat','started','progress','handoff','blocked','unblocked','completed','cancelled','lease_expired')),
  agent_id text not null references public.ai_agents(agent_id),
  idempotency_key text not null unique,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists ai_tasks_runnable_idx on public.ai_tasks(status, priority, created_at);
create index if not exists ai_tasks_lease_idx on public.ai_tasks(lease_expires_at) where lease_expires_at is not null;
create index if not exists ai_task_events_task_idx on public.ai_task_events(task_id, created_at desc);

-- Atomic task claim. The UPDATE itself is the compare-and-set boundary.
create or replace function public.ai_claim_task(
  p_task_id uuid,
  p_agent_id text,
  p_idempotency_key text,
  p_lease_seconds integer default 300
) returns public.ai_tasks
language plpgsql
as $$
declare
  v_task public.ai_tasks;
begin
  insert into public.ai_agents(agent_id, last_seen_at)
  values (p_agent_id, now())
  on conflict (agent_id) do update set last_seen_at = excluded.last_seen_at;

  if exists(select 1 from public.ai_task_events where idempotency_key = p_idempotency_key) then
    select * into v_task from public.ai_tasks where task_id = p_task_id;
    return v_task;
  end if;

  update public.ai_tasks
     set status = 'claimed',
         claimed_by = p_agent_id,
         lease_expires_at = now() + make_interval(secs => greatest(p_lease_seconds, 30)),
         updated_at = now(),
         version = version + 1
   where task_id = p_task_id
     and status in ('open','handoff','claimed','working')
     and (claimed_by is null or lease_expires_at is null or lease_expires_at <= now() or claimed_by = p_agent_id)
  returning * into v_task;

  if not found then
    raise exception 'task_not_claimable';
  end if;

  insert into public.ai_task_events(task_id,event_type,agent_id,idempotency_key,payload)
  values (p_task_id,'claimed',p_agent_id,p_idempotency_key,jsonb_build_object('lease_expires_at',v_task.lease_expires_at));

  return v_task;
end;
$$;

create or replace function public.ai_heartbeat(
  p_task_id uuid,
  p_agent_id text,
  p_idempotency_key text,
  p_lease_seconds integer default 300
) returns public.ai_tasks
language plpgsql
as $$
declare
  v_task public.ai_tasks;
begin
  if exists(select 1 from public.ai_task_events where idempotency_key = p_idempotency_key) then
    select * into v_task from public.ai_tasks where task_id = p_task_id;
    return v_task;
  end if;

  update public.ai_tasks
     set lease_expires_at = now() + make_interval(secs => greatest(p_lease_seconds, 30)),
         updated_at = now(),
         version = version + 1
   where task_id = p_task_id
     and claimed_by = p_agent_id
     and status in ('claimed','working')
     and lease_expires_at > now()
  returning * into v_task;

  if not found then raise exception 'lease_not_owned_or_expired'; end if;

  update public.ai_agents set last_seen_at = now() where agent_id = p_agent_id;
  insert into public.ai_task_events(task_id,event_type,agent_id,idempotency_key,payload)
  values (p_task_id,'heartbeat',p_agent_id,p_idempotency_key,jsonb_build_object('lease_expires_at',v_task.lease_expires_at));
  return v_task;
end;
$$;
