from supabase import create_client, Client
from config import settings

# Anon client — respects RLS; use in API routes with user JWT
def get_anon_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_anon_key)

# Service role client — bypasses RLS; use only in scheduler/background jobs and admin ops
service_client: Client = create_client(
    settings.supabase_url,
    settings.supabase_service_role_key,
)
