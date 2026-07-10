-- ================================================================
-- LinkedIn Copilot — Supabase Initial Migration
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor)
-- ================================================================

-- ── LinkedIn Profiles table (extends auth.users) ─────────────────
CREATE TABLE IF NOT EXISTS public.linkedin_profiles (
    id                   UUID REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
    role                 TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    display_name         TEXT,
    linkedin_email       TEXT,
    conversation_url     TEXT,
    nvidia_api_key       TEXT,          -- encrypted at app layer
    session_ready        BOOLEAN NOT NULL DEFAULT FALSE,
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── LinkedIn Message queue table ─────────────────────────────────
CREATE TABLE IF NOT EXISTS public.linkedin_message_queue (
    id            BIGSERIAL PRIMARY KEY,
    user_id       UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    event_urn     TEXT NOT NULL,
    activity_urn  TEXT,
    raw_data      JSONB,
    status        TEXT NOT NULL DEFAULT 'PENDING'
                  CHECK (status IN ('PENDING','PROCESSING','DONE','FAILED','DEAD')),
    retry_count   INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at  TIMESTAMPTZ,

    UNIQUE (user_id, event_urn)
);

-- Index for efficient queue polling per user
CREATE INDEX IF NOT EXISTS idx_linkedin_queue_user_status
    ON public.linkedin_message_queue(user_id, status, created_at);

-- ── Auto-create profile on user creation ────────────────────────
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
BEGIN
    INSERT INTO public.linkedin_profiles (id, display_name)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'display_name', NEW.email)
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ── Auto-update updated_at ───────────────────────────────────────
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_linkedin_profiles_updated_at ON public.linkedin_profiles;
CREATE TRIGGER set_linkedin_profiles_updated_at
    BEFORE UPDATE ON public.linkedin_profiles
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ── Row Level Security ───────────────────────────────────────────
ALTER TABLE public.linkedin_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.linkedin_message_queue ENABLE ROW LEVEL SECURITY;

-- Users can read/update only their own profile
CREATE POLICY "users_own_profile" ON public.linkedin_profiles
    FOR ALL USING (auth.uid() = id);

-- Users can read only their own queue rows
CREATE POLICY "users_own_queue" ON public.linkedin_message_queue
    FOR SELECT USING (auth.uid() = user_id);

-- ── NOTE: Background scheduler uses SERVICE ROLE KEY ────────────
-- Service role bypasses RLS automatically.
-- Never expose the service role key to the frontend.
