"""
LinkedIn Copilot — Application Entry Point

Starts FastAPI + APScheduler in a single async process.
Serves:
  • /api/v1/...  — versioned REST API
  • /            — web UI (Jinja2 templates)
  • /docs        — Swagger UI (disabled in production)

CLI commands:
  python main.py                          → run the server
  python main.py create-admin <email> <password> <name>
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fastapi.middleware.cors import CORSMiddleware

from api.v1 import router as v1_router
from config import settings
from scheduler.jobs import scheduler, bootstrap_all_users
from storage.sheets import ensure_header

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("Starting LinkedIn Copilot...")

    # Ensure Google Sheet has a header row
    try:
        ensure_header()
    except Exception as e:
        logger.warning("Could not ensure sheet header: %s", e)

    # Bootstrap per-user scheduler jobs
    bootstrap_all_users()
    scheduler.start()
    logger.info("Scheduler started.")

    yield  # App is running

    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped.")


app = FastAPI(
    title="LinkedIn Copilot",
    version="1.0.0",
    description="Multi-tenant LinkedIn post monitoring and summarization service.",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# Enable CORS for frontend API calls
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Static files and templates ─────────────────────────────────────────────
# server/ → ../client/ (resolved relative to this file for robustness)
_BASE = Path(__file__).parent.parent / "client"
app.mount("/static", StaticFiles(directory=str(_BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(_BASE / "templates"))


# ── API routes ───────────────────────────────────────────────────────────────
app.include_router(v1_router)


# ── Frontend routes ──────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def user_dashboard(request: Request):
    return templates.TemplateResponse("user/dashboard.html", {"request": request})


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_dashboard(request: Request):
    return templates.TemplateResponse("admin/dashboard.html", {"request": request})


# ── CLI: create-admin ────────────────────────────────────────────────────────

def _create_admin(email: str, password: str, display_name: str):
    from storage.supabase import service_client
    from storage.profiles import update_profile

    print(f"Creating admin: {email}...")
    response = service_client.auth.admin.create_user(
        {
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"display_name": display_name},
        }
    )
    user_id = str(response.user.id)
    update_profile(user_id, {"role": "admin", "display_name": display_name})
    print(f"✅ Admin created. user_id={user_id}")


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) >= 5 and sys.argv[1] == "create-admin":
        _create_admin(
            email=sys.argv[2],
            password=sys.argv[3],
            display_name=sys.argv[4],
        )
    else:
        uvicorn.run(
            "main:app",
            host=settings.host,
            port=settings.port,
            reload=settings.debug,
        )
