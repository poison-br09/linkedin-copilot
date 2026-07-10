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


@router.post("/trigger-watch", summary="Manually trigger conversation scrape")
async def trigger_watch(user: Annotated[dict, Depends(get_current_user)]):
    from collector.watcher import watch
    from storage.profiles import get_profile
    profile = get_profile(user["id"])
    if not profile or not profile.get("session_ready"):
        return {"success": False, "message": "LinkedIn session not ready."}
    conversation_url = profile.get("conversation_url", "")
    new_count = await watch(user["id"], conversation_url)
    return {"success": True, "new_messages_queued": new_count}


@router.post("/trigger-process", summary="Manually trigger queue processing")
async def trigger_process(user: Annotated[dict, Depends(get_current_user)]):
    from processor.queue_worker import process_user_queue
    process_user_queue(user["id"])
    return {"success": True, "message": "Queue processing triggered."}
