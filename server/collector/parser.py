"""
LinkedIn DOM parser.

LinkedIn changes its markup frequently. Selectors here are best-effort
and may need updating. Each extractor returns None gracefully on failure
rather than raising, so a single broken selector doesn't drop the message.
"""

import logging
import re
from typing import Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)

# ── Conversation message selectors ──────────────────────────────────────────
MSG_CONTAINER = ".msg-s-message-list__event"
MSG_URN_ATTR = "data-event-urn"

# ── Embedded post card selectors ─────────────────────────────────────────────
POST_CARD = "article.feed-shared-update-v2, div[data-urn]"
POST_URN_ATTR = "data-urn"

AUTHOR_NAME = (
    ".update-components-actor__title span[aria-hidden='true'], "
    ".feed-shared-actor__title"
)
AUTHOR_HEADLINE = (
    ".update-components-actor__description span[aria-hidden='true'], "
    ".feed-shared-actor__description"
)
POST_BODY = (
    ".feed-shared-update-v2__description span[dir], "
    ".feed-shared-text"
)
SENDER_NAME = ".msg-s-event-listitem__name, .msg-s-message-group__name"
MSG_TIMESTAMP = "time.msg-s-message-group__timestamp"


def _text(el, default: str = "") -> str:
    if el is None:
        return default
    return (el.inner_text() if hasattr(el, "inner_text") else str(el)).strip()


async def extract_messages(page: Page) -> list[dict]:
    """
    Extract all messages from the open LinkedIn conversation page.
    Returns a list of raw message dicts (only those containing a post card).
    """
    messages = []
    try:
        msg_elements = await page.query_selector_all(MSG_CONTAINER)
    except Exception as e:
        logger.error("Failed to query message elements: %s", e)
        return []

    for el in msg_elements:
        try:
            # Extract event URN (message ID)
            event_urn = await el.get_attribute(MSG_URN_ATTR)
            if not event_urn:
                # Try to find it in a child element
                urn_el = await el.query_selector(f"[{MSG_URN_ATTR}]")
                event_urn = await urn_el.get_attribute(MSG_URN_ATTR) if urn_el else None

            if not event_urn:
                continue

            # Check if message contains an embedded post card
            post_card = await el.query_selector(POST_CARD)
            
            # Check for regular text message containing a direct LinkedIn post URL
            msg_body_el = await el.query_selector(".msg-s-event-listitem__body, .msg-s-event-listitem__copy")
            msg_text = await msg_body_el.inner_text() if msg_body_el else ""
            
            post_url = None
            url_match = re.search(r"(https?://www\.linkedin\.com/(?:feed/update|posts)/[^\s\)\]\"']+)", msg_text)
            if url_match:
                post_url = url_match.group(1)

            if not post_card and not post_url:
                continue

            # Extract sender (the person who shared in the DM)
            sender_el = await el.query_selector(SENDER_NAME)
            sender = await sender_el.inner_text() if sender_el else ""

            # Extract timestamp
            ts_el = await el.query_selector(MSG_TIMESTAMP)
            timestamp = await ts_el.get_attribute("datetime") if ts_el else ""

            if post_card:
                # Extract post data from the card
                post_data = await _extract_post_card(post_card)
            else:
                # Construct post data from plain text link
                activity_urn = None
                urn_match = re.search(r"activity:(\d+)", post_url)
                if urn_match:
                    activity_urn = f"urn:li:activity:{urn_match.group(1)}"
                else:
                    post_id_match = re.search(r"-(\d+)", post_url)
                    if post_id_match:
                        activity_urn = f"urn:li:activity:{post_id_match.group(1)}"
                
                post_data = {
                    "activity_urn": activity_urn or f"urn:li:text_link:{event_urn}",
                    "author": "Link Shared in DM",
                    "author_headline": "",
                    "post_body": "Post link shared as text: " + post_url,
                    "post_url": post_url,
                    "urls": [post_url],
                }

            messages.append(
                {
                    "event_urn": event_urn.strip(),
                    "sender": sender.strip(),
                    "timestamp": timestamp.strip(),
                    **post_data,
                }
            )
        except Exception as e:
            logger.warning("Error parsing message element: %s", e)
            continue

    logger.info("Extracted %d post messages from conversation", len(messages))
    return messages


async def _extract_post_card(card) -> dict:
    """Extract structured data from a LinkedIn post card element."""

    async def safe_text(selector: str) -> str:
        try:
            el = await card.query_selector(selector)
            return (await el.inner_text()).strip() if el else ""
        except Exception:
            return ""

    async def safe_attr(selector: str, attr: str) -> str:
        try:
            el = await card.query_selector(selector)
            return (await el.get_attribute(attr) or "").strip() if el else ""
        except Exception:
            return ""

    activity_urn = await safe_attr(f"[{POST_URN_ATTR}]", POST_URN_ATTR)
    author = await safe_text(AUTHOR_NAME)
    author_headline = await safe_text(AUTHOR_HEADLINE)
    post_body = await safe_text(POST_BODY)

    # Build post URL from activity URN
    post_url = ""
    if activity_urn:
        # Extract numeric ID from URN like "urn:li:activity:1234567890"
        match = re.search(r"activity:(\d+)", activity_urn)
        if match:
            post_url = f"https://www.linkedin.com/feed/update/urn:li:activity:{match.group(1)}/"

    # Extract URLs from body text
    urls = re.findall(r"https?://[^\s\)\]\"']+", post_body)

    return {
        "activity_urn": activity_urn,
        "author": author,
        "author_headline": author_headline,
        "post_body": post_body,
        "post_url": post_url,
        "urls": list(set(urls)),
    }
