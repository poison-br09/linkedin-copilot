"""
LinkedIn connect/session management endpoints.

Flow:
  POST /linkedin/connect      → start Playwright login (returns requires_otp if 2FA)
  POST /linkedin/verify-otp  → complete 2FA and save session
  GET  /linkedin/status       → check if session is valid
  POST /linkedin/disconnect   → delete session
"""

import secrets
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.v1.deps import get_current_user
from collector.session import save_context, delete_session, session_exists
from scheduler.jobs import register_user_jobs
from storage.profiles import update_profile

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory store for pending 2FA sessions
# Maps pending_session_id → (playwright_instance, browser_context, page)
_pending_sessions: dict[str, tuple] = {}


class ConnectRequest(BaseModel):
    linkedin_email: str
    linkedin_password: str


class ConnectResponse(BaseModel):
    success: bool
    requires_otp: bool = False
    pending_session_id: Optional[str] = None
    message: str


class OTPRequest(BaseModel):
    pending_session_id: str
    otp: str


@router.post("/connect", response_model=ConnectResponse, summary="Connect LinkedIn account")
async def connect_linkedin(
    body: ConnectRequest,
    user: Annotated[dict, Depends(get_current_user)],
):
    """
    Launches a Playwright browser, logs into LinkedIn with the user's credentials.
    If 2FA is required, returns a pending_session_id for OTP submission.
    """
    from playwright.async_api import async_playwright

    user_id = user["id"]
    pw_manager = async_playwright()
    pw = await pw_manager.__aenter__()

    try:
        browser = await pw.chromium.launch(headless=True)
        # Use a realistic desktop browser User-Agent and viewport to avoid immediate captcha/bot detection
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        
        # Wait for the login fields to appear (supporting multiple common selectors)
        try:
            await page.wait_for_selector('input[type="email"]:visible', timeout=15000)
        except Exception:
            current_url = page.url
            logger.error("LinkedIn login elements not found. Page URL: %s", current_url)
            # Check if we were redirected to a security checkpoint/captcha immediately
            if "checkpoint" in current_url or "challenge" in current_url:
                raise HTTPException(
                    status_code=400,
                    detail="LinkedIn triggered a security check/captcha. Please try connecting again or try from a different network."
                )
            raise HTTPException(
                status_code=400, 
                detail=f"Login page did not load correctly. (URL: {current_url})"
            )

        await page.fill('input[type="email"]:visible', body.linkedin_email)
        await page.fill('input[type="password"]:visible', body.linkedin_password)
        
        # Click the Sign in button using exact role locator, with fallback to visible submit
        try:
            await page.get_by_role("button", name="Sign in", exact=True).click()
        except Exception:
            await page.click('button[type="submit"]:visible')
            
        await page.wait_for_timeout(4000)

        current_url = page.url

        # ── Check for 2FA page ────────────────────────────────────────────
        if "checkpoint" in current_url or "challenge" in current_url:
            session_id = secrets.token_urlsafe(16)
            _pending_sessions[session_id] = (pw_manager, browser, context, page, user_id)
            logger.info("2FA or phone verification required for user %s. Pending session: %s", user_id, session_id)
            return ConnectResponse(
                success=False,
                requires_otp=True,
                pending_session_id=session_id,
                message="Security check required. Please approve the prompt on your phone or enter the OTP.",
            )

        # ── Successful login (no 2FA) ─────────────────────────────────────
        if "feed" in current_url or "linkedin.com/in/" in current_url or current_url == "https://www.linkedin.com/":
            await save_context(context, user_id)
            await browser.close()
            await pw_manager.__aexit__(None, None, None)

            update_profile(user_id, {"session_ready": True, "linkedin_email": body.linkedin_email})
            register_user_jobs(user_id)

            return ConnectResponse(success=True, message="LinkedIn connected successfully.")

        # ── Login failed (wrong credentials, captcha, etc.) ───────────────
        await browser.close()
        await pw_manager.__aexit__(None, None, None)
        raise HTTPException(status_code=400, detail="Login failed. Check your credentials.")

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("LinkedIn connect error for user %s: %s", user_id, exc)
        try:
            await pw_manager.__aexit__(None, None, None)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Login error: {exc}")


@router.post("/verify-otp", response_model=ConnectResponse, summary="Submit 2FA OTP")
async def verify_otp(
    body: OTPRequest,
    user: Annotated[dict, Depends(get_current_user)],
):
    """Submit the OTP or verify phone approval for a pending 2FA LinkedIn login."""
    user_id = user["id"]
    pending = _pending_sessions.get(body.pending_session_id)

    if not pending:
        raise HTTPException(status_code=400, detail="Invalid or expired pending session.")

    pw_manager, browser, context, page, session_user_id = pending

    if session_user_id != user_id:
        raise HTTPException(status_code=403, detail="Session does not belong to you.")

    try:
        # Check if the page has already redirected to the feed (phone notification approved)
        current_url = page.url
        if "feed" in current_url or "linkedin.com/in/" in current_url or current_url == "https://www.linkedin.com/":
            await save_context(context, user_id)
            await browser.close()
            await pw_manager.__aexit__(None, None, None)
            if body.pending_session_id in _pending_sessions:
                del _pending_sessions[body.pending_session_id]

            update_profile(user_id, {"session_ready": True})
            register_user_jobs(user_id)
            return ConnectResponse(success=True, message="LinkedIn connected successfully via phone approval.")

        # Otherwise, try to fill the OTP if provided
        if body.otp:
            otp_input = await page.query_selector("input[name='pin'], input[autocomplete='one-time-code'], #input__phone_verification_pin")
            if not otp_input:
                # If there's no input but user submitted a code, check if we're still waiting for phone approval
                raise HTTPException(
                    status_code=400, 
                    detail="Verification code input field not found. If you approved on your phone, please try again."
                )

            await otp_input.fill(body.otp)
            await page.click('button[type="submit"]:visible')
            await page.wait_for_timeout(4000)

        # Re-check if successfully logged in now
        current_url = page.url
        if "feed" in current_url or "linkedin.com/in/" in current_url or current_url == "https://www.linkedin.com/":
            await save_context(context, user_id)
            await browser.close()
            await pw_manager.__aexit__(None, None, None)
            if body.pending_session_id in _pending_sessions:
                del _pending_sessions[body.pending_session_id]

            update_profile(user_id, {"session_ready": True})
            register_user_jobs(user_id)
            return ConnectResponse(success=True, message="LinkedIn connected successfully.")

        raise HTTPException(
            status_code=400, 
            detail="Verification still pending. If using phone approval, make sure you tapped 'Yes, it's me' and submit again."
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("OTP verification error: %s", exc)
        raise HTTPException(status_code=500, detail=f"OTP error: {exc}")


@router.get("/status", summary="Check LinkedIn session status")
async def session_status(user: Annotated[dict, Depends(get_current_user)]):
    from storage.profiles import get_profile
    profile = get_profile(user["id"])
    ready = profile.get("session_ready", False) if profile else False
    file_exists = session_exists(user["id"])
    return {
        "session_ready": ready and file_exists,
        "session_file_exists": file_exists,
    }


@router.post("/disconnect", summary="Disconnect LinkedIn session")
async def disconnect(user: Annotated[dict, Depends(get_current_user)]):
    from scheduler.jobs import remove_user_jobs
    user_id = user["id"]
    delete_session(user_id)
    update_profile(user_id, {"session_ready": False})
    remove_user_jobs(user_id)
    return {"detail": "LinkedIn session disconnected."}
