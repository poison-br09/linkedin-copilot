"""
Shared FastAPI dependencies for API v1.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from storage.supabase import get_anon_client
from storage.profiles import get_profile

bearer = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
) -> dict:
    """Verify Supabase JWT and return the user dict."""
    token = credentials.credentials
    try:
        client = get_anon_client()
        response = client.auth.get_user(token)
        if not response or not response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token.",
            )
        return {"id": response.user.id, "email": response.user.email}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
        ) from exc


async def get_current_profile(
    user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Return the full profile row for the authenticated user."""
    profile = get_profile(user["id"])
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return profile


async def require_admin(
    profile: Annotated[dict, Depends(get_current_profile)],
) -> dict:
    """Raise 403 if the user is not an admin."""
    if profile.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return profile
