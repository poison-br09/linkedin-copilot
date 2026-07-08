"""
Admin-only endpoints for user management.
All routes require admin role (enforced by require_admin dependency).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from api.v1.deps import require_admin
from scheduler.jobs import register_user_jobs, remove_user_jobs
from storage.profiles import (
    get_all_active_profiles,
    get_profile,
    set_active,
    update_profile,
)
from storage.supabase import service_client

router = APIRouter()


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    conversation_url: str | None = None
    is_active: bool | None = None


# ── Create user ──────────────────────────────────────────────────────────────

@router.post("/users", status_code=status.HTTP_201_CREATED, summary="Create a new user")
async def create_user(
    body: CreateUserRequest,
    _admin: Annotated[dict, Depends(require_admin)],
):
    """Admin creates a user account. The user can then log in and connect LinkedIn."""
    try:
        response = service_client.auth.admin.create_user(
            {
                "email": body.email,
                "password": body.password,
                "email_confirm": True,
                "user_metadata": {"display_name": body.display_name},
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create user: {exc}",
        ) from exc

    user_id = str(response.user.id)
    # Update display_name in profile (trigger already created the row)
    update_profile(user_id, {"display_name": body.display_name})

    return {"user_id": user_id, "email": body.email, "display_name": body.display_name}


# ── List users ───────────────────────────────────────────────────────────────

@router.get("/users", summary="List all users")
async def list_users(_admin: Annotated[dict, Depends(require_admin)]):
    profiles = get_all_active_profiles()
    return {"users": profiles, "count": len(profiles)}


# ── Get single user ──────────────────────────────────────────────────────────

@router.get("/users/{user_id}", summary="Get user details")
async def get_user(
    user_id: str,
    _admin: Annotated[dict, Depends(require_admin)],
):
    profile = get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found.")
    return profile


# ── Update user ──────────────────────────────────────────────────────────────

@router.patch("/users/{user_id}", summary="Update user config")
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    _admin: Annotated[dict, Depends(require_admin)],
):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update.")
    updated = update_profile(user_id, data)
    return {"updated": updated}


# ── Deactivate user ──────────────────────────────────────────────────────────

@router.delete("/users/{user_id}", summary="Deactivate a user")
async def deactivate_user(
    user_id: str,
    _admin: Annotated[dict, Depends(require_admin)],
):
    set_active(user_id, False)
    remove_user_jobs(user_id)
    return {"detail": f"User {user_id} deactivated and jobs stopped."}


# ── Reset LinkedIn session ───────────────────────────────────────────────────

@router.post("/users/{user_id}/reset-session", summary="Reset a user's LinkedIn session")
async def reset_session(
    user_id: str,
    _admin: Annotated[dict, Depends(require_admin)],
):
    from collector.session import delete_session
    delete_session(user_id)
    update_profile(user_id, {"session_ready": False})
    remove_user_jobs(user_id)
    return {"detail": f"Session reset for user {user_id}. User must reconnect LinkedIn."}
