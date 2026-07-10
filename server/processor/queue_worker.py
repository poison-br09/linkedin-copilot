"""
Queue worker — processes PENDING messages for a single user.

Flow per row:
  PENDING → PROCESSING → (Nemotron) → (Sheets) → DONE
                                               ↘ FAILED/DEAD
"""

import logging
from openai import RateLimitError

from config import settings
from processor.summarizer import summarize
from storage import queue_db, sheets
from storage.profiles import get_profile

logger = logging.getLogger(__name__)


def process_user_queue(user_id: str) -> None:
    """
    Pick up to PROCESSOR_BATCH_SIZE pending messages for the user,
    summarize each via Nemotron, append to Google Sheets, and mark DONE.
    """
    profile = get_profile(user_id)
    if not profile:
        logger.warning("No profile found for user %s. Skipping.", user_id)
        return

    api_key = profile.get("nvidia_api_key") or settings.nvidia_api_key
    receiver_name = profile.get("display_name") or user_id

    # Reset any stuck PROCESSING rows from a previous crash
    queue_db.reset_stuck_processing(user_id)

    batch = queue_db.get_pending_batch(user_id)
    if not batch:
        logger.debug("No pending messages for user %s.", user_id)
        return

    logger.info("Processing %d messages for user %s.", len(batch), user_id)

    for row in batch:
        row_id = row["id"]
        event_urn = row.get("event_urn", "")
        raw_data = row.get("raw_data") or {}

        queue_db.mark_processing(row_id)

        try:
            result = summarize(raw_data, api_key=api_key)
        except RateLimitError:
            logger.warning("Rate limited on event_urn=%s. Will retry later.", event_urn)
            queue_db.mark_failed(row_id)
            # Stop processing this batch — no point hammering the API
            break
        except ValueError as e:
            logger.error("LLM parse error for event_urn=%s: %s", event_urn, e)
            queue_db.mark_failed(row_id)
            continue
        except Exception as e:
            logger.error("Unexpected error for event_urn=%s: %s", event_urn, e)
            queue_db.mark_failed(row_id)
            continue

        try:
            sheets.append_row(
                {
                    "receiver": receiver_name,
                    "sender": raw_data.get("sender", ""),
                    "timestamp": raw_data.get("timestamp", ""),
                    "event_urn": event_urn,
                    "activity_urn": row.get("activity_urn", ""),
                    "author": raw_data.get("author", ""),
                    "author_headline": raw_data.get("author_headline", ""),
                    "category": result["category"],
                    "title": result["title"],
                    "summary": result["summary"],
                    "links": result["links"],
                    "post_url": raw_data.get("post_url", ""),
                }
            )
        except Exception as e:
            logger.error("Failed to write to sheet for event_urn=%s: %s", event_urn, e)
            queue_db.mark_failed(row_id)
            continue

        queue_db.mark_done(row_id, result)
        logger.info("Done: event_urn=%s", event_urn)
