import json
import logging
import os
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext, Playwright

from config import settings

logger = logging.getLogger(__name__)


def _session_path(user_id: str) -> Path:
    path = Path(settings.sessions_dir) / user_id
    path.mkdir(parents=True, exist_ok=True)
    return path / "state.json"


def session_exists(user_id: str) -> bool:
    return _session_path(user_id).exists()


def delete_session(user_id: str) -> None:
    p = _session_path(user_id)
    if p.exists():
        p.unlink()
        logger.info("Session deleted for user %s", user_id)


async def load_context(p: Playwright, user_id: str) -> Optional[BrowserContext]:
    """Load a saved Playwright session for a user. Returns None if no session exists."""
    path = _session_path(user_id)
    if not path.exists():
        logger.warning("No session found for user %s", user_id)
        return None
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(storage_state=str(path))
    logger.info("Session loaded for user %s", user_id)
    return context


async def save_context(context: BrowserContext, user_id: str) -> None:
    """Persist a Playwright context's cookies/storage to disk."""
    path = _session_path(user_id)
    await context.storage_state(path=str(path))
    # Restrict file permissions: owner read/write only
    os.chmod(path, 0o600)
    logger.info("Session saved for user %s", user_id)
