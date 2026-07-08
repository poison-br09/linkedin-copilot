from typing import Optional
from storage.supabase import service_client

TABLE = "profiles"


def get_profile(user_id: str) -> Optional[dict]:
    result = (
        service_client.table(TABLE)
        .select("*")
        .eq("id", user_id)
        .single()
        .execute()
    )
    return result.data


def get_all_active_profiles() -> list[dict]:
    """Return all active users — used by scheduler to register jobs."""
    result = (
        service_client.table(TABLE)
        .select("*")
        .eq("is_active", True)
        .execute()
    )
    return result.data or []


def update_profile(user_id: str, data: dict) -> dict:
    result = (
        service_client.table(TABLE)
        .update(data)
        .eq("id", user_id)
        .execute()
    )
    return result.data[0] if result.data else {}


def set_session_ready(user_id: str, ready: bool):
    service_client.table(TABLE).update(
        {"session_ready": ready}
    ).eq("id", user_id).execute()


def set_active(user_id: str, active: bool):
    service_client.table(TABLE).update(
        {"is_active": active}
    ).eq("id", user_id).execute()


def create_admin_profile(user_id: str, display_name: str):
    """Called by the create-admin CLI command after creating the auth user."""
    service_client.table(TABLE).upsert(
        {"id": user_id, "role": "admin", "display_name": display_name}
    ).execute()
