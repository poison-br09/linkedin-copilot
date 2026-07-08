from datetime import datetime, timezone
from typing import Optional
from config import settings
from storage.supabase import service_client

TABLE = "message_queue"


class MessageStatus:
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DONE = "DONE"
    FAILED = "FAILED"
    DEAD = "DEAD"


def exists(user_id: str, event_urn: str) -> bool:
    result = (
        service_client.table(TABLE)
        .select("id")
        .eq("user_id", user_id)
        .eq("event_urn", event_urn)
        .execute()
    )
    return len(result.data) > 0


def insert_pending(
    user_id: str,
    event_urn: str,
    activity_urn: Optional[str],
    raw_data: dict,
) -> None:
    service_client.table(TABLE).upsert(
        {
            "user_id": user_id,
            "event_urn": event_urn,
            "activity_urn": activity_urn,
            "raw_data": raw_data,
            "status": MessageStatus.PENDING,
            "retry_count": 0,
        },
        on_conflict="user_id,event_urn",
    ).execute()


def get_pending_batch(user_id: str, limit: Optional[int] = None) -> list[dict]:
    limit = limit or settings.processor_batch_size
    result = (
        service_client.table(TABLE)
        .select("*")
        .eq("user_id", user_id)
        .in_("status", [MessageStatus.PENDING, MessageStatus.FAILED])
        .lt("retry_count", settings.max_retries)
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return result.data or []


def mark_processing(row_id: int) -> None:
    service_client.table(TABLE).update(
        {"status": MessageStatus.PROCESSING}
    ).eq("id", row_id).execute()


def mark_done(row_id: int) -> None:
    service_client.table(TABLE).update(
        {
            "status": MessageStatus.DONE,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", row_id).execute()


def mark_failed(row_id: int) -> None:
    result = (
        service_client.table(TABLE)
        .select("retry_count")
        .eq("id", row_id)
        .single()
        .execute()
    )
    current = result.data.get("retry_count", 0) if result.data else 0
    new_count = current + 1
    new_status = (
        MessageStatus.DEAD
        if new_count >= settings.max_retries
        else MessageStatus.FAILED
    )
    service_client.table(TABLE).update(
        {"status": new_status, "retry_count": new_count}
    ).eq("id", row_id).execute()


def reset_stuck_processing(user_id: str) -> None:
    """Move PROCESSING rows back to PENDING — fixes rows stuck after a crash."""
    service_client.table(TABLE).update(
        {"status": MessageStatus.PENDING}
    ).eq("user_id", user_id).eq("status", MessageStatus.PROCESSING).execute()


def get_queue_stats(user_id: str) -> dict:
    result = (
        service_client.table(TABLE)
        .select("status")
        .eq("user_id", user_id)
        .execute()
    )
    counts = {s: 0 for s in ["PENDING", "PROCESSING", "DONE", "FAILED", "DEAD"]}
    for row in result.data or []:
        s = row.get("status", "")
        if s in counts:
            counts[s] += 1
    return counts


def get_user_queue(
    user_id: str, limit: int = 50, offset: int = 0
) -> list[dict]:
    result = (
        service_client.table(TABLE)
        .select("id,event_urn,activity_urn,status,retry_count,created_at,processed_at,raw_data")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data or []
