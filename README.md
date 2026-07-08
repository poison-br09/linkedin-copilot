# LinkedIn Copilot

A multi-tenant background service that monitors LinkedIn 1:1 conversations, extracts shared posts, summarizes them via NVIDIA Nemotron, and writes results to a shared Google Sheet.

---

## Features

- **Multi-user** — each employee has their own isolated LinkedIn session and message queue
- **Two-stage pipeline** — Watcher (scrape → queue) and Processor (AI → Sheets) run independently
- **Supabase** — PostgreSQL + Auth + Row Level Security for zero data leakage between users
- **NVIDIA Nemotron** — free-tier LLM for post summarization
- **Google Sheets** — single shared sheet with Receiver + Sender columns for all users
- **Versioned REST API** — all endpoints under `/api/v1/`
- **Web UI** — admin dashboard and per-user dashboard

---

## Quick Start

### 1. Clone & enter the server

```bash
git clone <repo-url> && cd linkedin-copilot/server
```

### 2. Create & activate a virtual environment

```bash
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env with your Supabase URL/keys, NVIDIA key, and Google Sheet ID
```

### 5. Set up Supabase

- Go to your Supabase project → SQL Editor
- Run `supabase/migrations/001_initial.sql`

### 6. Set up Google Sheets

- Create a Google Cloud service account with **Google Sheets API** enabled
- Download the JSON key → save as `server/service_account.json`
- Share your Google Sheet with the service account email (Editor access)

### 7. Create the first admin

```bash
# From inside server/ with venv active
python main.py create-admin admin@company.com YourPassword "Admin Name"
```

### 8. Run the server

```bash
# Development (with auto-reload)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Visit http://localhost:8000
```

---

## API Reference

All endpoints are versioned under `/api/v1/`. Enable Swagger UI by setting `DEBUG=true` and visiting `/docs`.

### Authentication
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/auth/login` | Login, returns JWT |

### Admin (requires admin role)
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/admin/users` | Create user |
| `GET` | `/api/v1/admin/users` | List all users |
| `PATCH` | `/api/v1/admin/users/{id}` | Update user |
| `DELETE` | `/api/v1/admin/users/{id}` | Deactivate user |
| `POST` | `/api/v1/admin/users/{id}/reset-session` | Reset LinkedIn session |

### LinkedIn
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/linkedin/connect` | Start LinkedIn login |
| `POST` | `/api/v1/linkedin/verify-otp` | Submit 2FA OTP |
| `GET` | `/api/v1/linkedin/status` | Session status |
| `POST` | `/api/v1/linkedin/disconnect` | Remove session |

### Config & Status
| Method | Path | Description |
|---|---|---|
| `GET/PUT` | `/api/v1/config` | User config |
| `GET` | `/api/v1/status` | Queue stats |
| `GET` | `/api/v1/status/queue` | Message queue |

---

## Architecture

```
POST /api/v1/linkedin/connect
    → Playwright login → sessions/{user_id}/state.json

Scheduler (every 1 hr per user):
    watcher_job → Playwright → LinkedIn → Supabase queue (PENDING)

Scheduler (every 10 min per user):
    processor_job → Supabase (PENDING) → Nemotron → Google Sheets → (DONE)
```

---

## Google Sheet Columns

`Receiver | Sender | Timestamp | Event URN | Activity URN | Author | Author Headline | Category | Title | Summary | Links | Post URL`

---

## Environment Variables

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (server only) |
| `SECRET_KEY` | App secret for encryption |
| `NVIDIA_API_KEY` | NVIDIA Nemotron API key |
| `GOOGLE_SHEET_ID` | Target Google Sheet ID |
| `GOOGLE_SERVICE_ACCOUNT_PATH` | Path to service account JSON |
| `WATCHER_INTERVAL_HOURS` | How often to scrape LinkedIn (default: 1) |
| `PROCESSOR_INTERVAL_MINUTES` | How often to process queue (default: 10) |
| `DEBUG` | Enable Swagger UI and hot reload |

---

## Deployment (Server)

```bash
cd server

# Create and activate venv
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt && playwright install chromium --with-deps

# Run (single worker — required, see note below)
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

> **⚠️ Single worker only** — the APScheduler and in-memory 2FA session state (`_pending_sessions`) require a single process. Do not increase `--workers`.
