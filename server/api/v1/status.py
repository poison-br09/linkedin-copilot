"""Status and queue inspection endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.v1.deps import get_current_user
from storage.queue_db import get_queue_stats, get_user_queue

router = APIRouter()


@router.get("", summary="Get queue stats for the current user")
async def get_status(user: Annotated[dict, Depends(get_current_user)]):
    stats = get_queue_stats(user["id"])
    return {"user_id": user["id"], "queue_stats": stats}


@router.get("/queue", summary="List message queue for the current user")
async def get_queue(
    user: Annotated[dict, Depends(get_current_user)],
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    rows = get_user_queue(user["id"], limit=limit, offset=offset)
    return {"rows": rows, "count": len(rows)}
