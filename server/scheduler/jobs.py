"""
APScheduler job definitions.

Two job types per active user:
  • watcher_job   — every WATCHER_INTERVAL_HOURS hours
  • processor_job — every PROCESSOR_INTERVAL_MINUTES minutes

Jobs are registered at startup for all existing active users.
New users get jobs registered when they complete LinkedIn setup.
"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from collector.watcher import watch
from processor.queue_worker import process_user_queue
from storage.profiles import get_all_active_profiles, get_profile
from config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


# ── Job functions ────────────────────────────────────────────────────────────

async def watcher_job(user_id: str) -> None:
    logger.info("[WATCHER] Starting for user %s", user_id)
    profile = get_profile(user_id)
    if not profile or not profile.get("session_ready"):
        logger.warning("[WATCHER] User %s session not ready. Skipping.", user_id)
        return
    conversation_url = profile.get("conversation_url", "")
    await watch(user_id, conversation_url)


def processor_job(user_id: str) -> None:
    logger.info("[PROCESSOR] Starting for user %s", user_id)
    process_user_queue(user_id)


# ── Job registration ─────────────────────────────────────────────────────────

def register_user_jobs(user_id: str) -> None:
    """Register (or replace) watcher and processor jobs for a user."""
    watcher_id = f"watcher_{user_id}"
    processor_id = f"processor_{user_id}"

    # Remove existing jobs if present (e.g. config update)
    for jid in (watcher_id, processor_id):
        if scheduler.get_job(jid):
            scheduler.remove_job(jid)

    scheduler.add_job(
        watcher_job,
        "interval",
        hours=settings.watcher_interval_hours,
        args=[user_id],
        id=watcher_id,
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        processor_job,
        "interval",
        minutes=settings.processor_interval_minutes,
        args=[user_id],
        id=processor_id,
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Jobs registered for user %s", user_id)


def remove_user_jobs(user_id: str) -> None:
    """Remove all jobs for a deactivated/deleted user."""
    for jid in (f"watcher_{user_id}", f"processor_{user_id}"):
        if scheduler.get_job(jid):
            scheduler.remove_job(jid)
    logger.info("Jobs removed for user %s", user_id)


def bootstrap_all_users() -> None:
    """Called at startup — register jobs for every active user."""
    profiles = get_all_active_profiles()
    logger.info("Bootstrapping scheduler for %d active users.", len(profiles))
    for profile in profiles:
        register_user_jobs(profile["id"])
