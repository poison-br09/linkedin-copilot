"""
LinkedIn conversation watcher.

For each active user with a valid session, this module:
  1. Opens their configured LinkedIn conversation URL via Playwright.
  2. Extracts all messages containing embedded post cards.
  3. Inserts new (unseen) messages into the Supabase queue as PENDING.
"""

import logging

from playwright.async_api import async_playwright

from collector import parser
from collector.session import load_context
from storage import queue_db

logger = logging.getLogger(__name__)


async def watch(user_id: str, conversation_url: str) -> int:
    """
    Scrape the LinkedIn conversation for the given user.
    Returns the number of new messages inserted into the queue.
    """
    if not conversation_url:
        logger.warning("User %s has no conversation_url configured. Skipping.", user_id)
        return 0

    new_count = 0
    async with async_playwright() as p:
        context = await load_context(p, user_id)
        if context is None:
            logger.warning(
                "User %s has no valid session. Skipping watcher run.", user_id
            )
            return 0

        page = await context.new_page()
        try:
            logger.info("Opening conversation for user %s ...", user_id)
            await page.goto(conversation_url, wait_until="domcontentloaded", timeout=30_000)

            # Wait for messages to load
            await page.wait_for_selector(
                ".msg-s-message-list__event",
                timeout=15_000,
            )

            # Scroll to load older messages if needed
            await _scroll_to_load(page)

            messages = await parser.extract_messages(page)
            logger.info(
                "User %s: found %d post messages in conversation.", user_id, len(messages)
            )

            for msg in messages:
                event_urn = msg.get("event_urn")
                if not event_urn:
                    continue
                if queue_db.exists(user_id, event_urn):
                    logger.debug("Already queued: %s", event_urn)
                    continue

                queue_db.insert_pending(
                    user_id=user_id,
                    event_urn=event_urn,
                    activity_urn=msg.get("activity_urn"),
                    raw_data=msg,
                )
                new_count += 1
                logger.info("Queued new message: %s", event_urn)

        except Exception as e:
            logger.error("Watcher error for user %s: %s", user_id, e)
        finally:
            await page.close()
            await context.browser.close()

    logger.info("Watcher done for user %s. New messages queued: %d", user_id, new_count)
    return new_count


async def _scroll_to_load(page) -> None:
    """Scroll the conversation container to trigger lazy-loaded messages."""
    try:
        container = await page.query_selector(".msg-s-message-list-container")
        if container:
            await page.evaluate(
                "(el) => { el.scrollTop = 0; }", container
            )
            await page.wait_for_timeout(2000)
    except Exception:
        pass
