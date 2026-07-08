"""User configuration endpoints."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.v1.deps import get_current_user, get_current_profile
from storage.profiles import update_profile

router = APIRouter()


class ConfigUpdate(BaseModel):
    conversation_url: Optional[str] = None
    nvidia_api_key: Optional[str] = None
    display_name: Optional[str] = None


class ConfigResponse(BaseModel):
    display_name: Optional[str]
    conversation_url: Optional[str]
    nvidia_api_key_set: bool
    session_ready: bool


@router.get("", response_model=ConfigResponse, summary="Get current user config")
async def get_config(
    profile: Annotated[dict, Depends(get_current_profile)],
):
    return ConfigResponse(
        display_name=profile.get("display_name"),
        conversation_url=profile.get("conversation_url"),
        nvidia_api_key_set=bool(profile.get("nvidia_api_key")),
        session_ready=profile.get("session_ready", False),
    )


@router.put("", response_model=ConfigResponse, summary="Update current user config")
async def update_config(
    body: ConfigUpdate,
    user: Annotated[dict, Depends(get_current_user)],
):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update.")

    update_profile(user["id"], data)
    from storage.profiles import get_profile
    profile = get_profile(user["id"])

    return ConfigResponse(
        display_name=profile.get("display_name"),
        conversation_url=profile.get("conversation_url"),
        nvidia_api_key_set=bool(profile.get("nvidia_api_key")),
        session_ready=profile.get("session_ready", False),
    )
