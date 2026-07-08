# LinkedIn Copilot — CLI Documentation

> **Status**: Planned (not yet implemented)
> The CLI will live in `client/cli/` and communicate with the existing `/api/v1/` REST API.
> No backend changes are required to add it.

---

## Overview

The CLI provides a terminal-first interface for managing the LinkedIn Copilot service.
It is intended for admins and power users who prefer the terminal over the web UI.

**Tech stack (planned)**: [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/) for pretty output.

---

## Installation (planned)

```bash
cd client/cli
pip install -r requirements.txt

# Make the command globally available
pip install -e .

# Then use:
copilot <command>
```

---

## Authentication

### `copilot login`

Log in to the LinkedIn Copilot service. Stores the JWT token locally.

```bash
copilot login
```

**Options:**
```
--email     TEXT    Your account email
--password  TEXT    Your account password
--host      TEXT    Server URL (default: http://localhost:8000)
```

**Example:**
```bash
copilot login --email jane@company.com --host https://myserver.com
# Prompts for password securely if not provided
```

**What it does:**
- Calls `POST /api/v1/auth/login`
- Stores the JWT token in `~/.copilot/config.json`
- Subsequent commands use this token automatically

---

### `copilot logout`

Clear the stored JWT token.

```bash
copilot logout
```

---

### `copilot whoami`

Show the currently logged-in user.

```bash
copilot whoami
```

**Output:**
```
Logged in as: jane@company.com (user)
Server: https://myserver.com
```

---

## User Commands (Admin only)

### `copilot add-user`

Create a new user account.

```bash
copilot add-user
```

**Options:**
```
--email     TEXT    New user's email          [required]
--name      TEXT    Display name              [required]
--password  TEXT    Temporary password        [required]
```

**Example:**
```bash
copilot add-user --email bob@company.com --name "Bob Smith" --password TempPass123
```

**What it does:**
- Calls `POST /api/v1/admin/users`
- Prints the created `user_id`

---

### `copilot list-users`

List all users and their status.

```bash
copilot list-users
```

**Output:**
```
┌─────────────────┬──────────────────────────────────┬─────────────┬──────────┐
│ Name            │ User ID                          │ LinkedIn    │ Active   │
├─────────────────┼──────────────────────────────────┼─────────────┼──────────┤
│ Jane Doe        │ 3f2a...                          │ ● Connected │ ✓ Active │
│ Bob Smith       │ 7c1b...                          │ ✗ Not set   │ ✓ Active │
└─────────────────┴──────────────────────────────────┴─────────────┴──────────┘
```

---

### `copilot remove-user`

Deactivate a user and stop their scheduler jobs.

```bash
copilot remove-user --user-id <user_id>
```

**Options:**
```
--user-id   TEXT    Target user's ID    [required]
```

---

### `copilot reset-session`

Force a user to re-connect their LinkedIn account.

```bash
copilot reset-session --user-id <user_id>
```

---

## LinkedIn Commands

### `copilot linkedin connect`

Connect your LinkedIn account by logging in via the server's Playwright browser.

```bash
copilot linkedin connect
```

**Options:**
```
--email     TEXT    Your LinkedIn email     [required]
--password  TEXT    Your LinkedIn password  [required]
```

**Flow:**
```
copilot linkedin connect --email me@gmail.com
→ Password: ****
→ Connecting…
→ ✓ Connected! (or prompts for OTP if 2FA is enabled)
```

**What it does:**
- Calls `POST /api/v1/linkedin/connect`
- If `requires_otp: true` → prompts for OTP interactively
- Calls `POST /api/v1/linkedin/verify-otp` with the entered code

---

### `copilot linkedin status`

Check if your LinkedIn session is active.

```bash
copilot linkedin status
```

**Output:**
```
LinkedIn session: ● Connected
Session file:     ✓ Exists
```

---

### `copilot linkedin disconnect`

Remove your LinkedIn session.

```bash
copilot linkedin disconnect
```

---

## Configuration Commands

### `copilot config set`

Update your configuration.

```bash
copilot config set --key <key> --value <value>
```

**Supported keys:**
```
conversation_url    The LinkedIn 1:1 conversation URL to monitor
nvidia_api_key      Your NVIDIA Nemotron API key
display_name        Your display name (shown in Google Sheet)
```

**Examples:**
```bash
copilot config set --key conversation_url --value "https://www.linkedin.com/messaging/thread/123/"
copilot config set --key nvidia_api_key --value "nvapi-..."
```

---

### `copilot config show`

Show your current configuration.

```bash
copilot config show
```

**Output:**
```
Display Name:        Jane Doe
Conversation URL:    https://www.linkedin.com/messaging/thread/123/
NVIDIA API Key:      nvapi-•••••••••• (set)
LinkedIn Session:    ● Connected
```

---

## Status & Queue Commands

### `copilot status`

Show queue statistics for your account.

```bash
copilot status
```

**Output:**
```
Queue Statistics
───────────────────────────────
  PENDING      3
  PROCESSING   0
  DONE         142
  FAILED       1
  DEAD         0
```

---

### `copilot queue`

List recent messages in your queue.

```bash
copilot queue
```

**Options:**
```
--limit     INT     Number of rows to show (default: 20)
--status    TEXT    Filter by status: PENDING, DONE, FAILED, etc.
```

**Output:**
```
┌──────────────────────┬─────────────┬─────────┬──────────────────────┐
│ Event URN            │ Status      │ Retries │ Created At           │
├──────────────────────┼─────────────┼─────────┼──────────────────────┤
│ urn:li:event:123456  │ DONE        │ 0       │ 2026-07-08 09:15:00  │
│ urn:li:event:789012  │ PENDING     │ 0       │ 2026-07-08 10:00:00  │
│ urn:li:event:345678  │ FAILED      │ 2       │ 2026-07-08 10:05:00  │
└──────────────────────┴─────────────┴─────────┴──────────────────────┘
```

---

## Global Options

These options work with every command:

```
--host      TEXT    Server base URL (overrides config)
--token     TEXT    JWT token (overrides stored token)
--json              Output raw JSON instead of formatted tables
--help              Show help for any command
```

**Examples:**
```bash
copilot status --host https://myserver.com
copilot list-users --json
copilot queue --status FAILED --limit 50
```

---

## Local Config File

The CLI stores its state in `~/.copilot/config.json`:

```json
{
  "host": "http://localhost:8000",
  "token": "eyJ..."
}
```

This file is created on first `copilot login` and updated on `copilot logout`.

---

## Command → API Mapping

| CLI Command | HTTP Method | API Endpoint |
|---|---|---|
| `copilot login` | `POST` | `/api/v1/auth/login` |
| `copilot add-user` | `POST` | `/api/v1/admin/users` |
| `copilot list-users` | `GET` | `/api/v1/admin/users` |
| `copilot remove-user` | `DELETE` | `/api/v1/admin/users/{id}` |
| `copilot reset-session` | `POST` | `/api/v1/admin/users/{id}/reset-session` |
| `copilot linkedin connect` | `POST` | `/api/v1/linkedin/connect` |
| `copilot linkedin verify-otp` | `POST` | `/api/v1/linkedin/verify-otp` |
| `copilot linkedin status` | `GET` | `/api/v1/linkedin/status` |
| `copilot linkedin disconnect` | `POST` | `/api/v1/linkedin/disconnect` |
| `copilot config set` | `PUT` | `/api/v1/config` |
| `copilot config show` | `GET` | `/api/v1/config` |
| `copilot status` | `GET` | `/api/v1/status` |
| `copilot queue` | `GET` | `/api/v1/status/queue` |

---

## Planned File Structure

```
client/
└── cli/
    ├── copilot/
    │   ├── __init__.py
    │   ├── main.py          # Typer app entry point
    │   ├── auth.py          # login, logout, whoami commands
    │   ├── admin.py         # add-user, list-users, remove-user
    │   ├── linkedin.py      # linkedin connect/status/disconnect
    │   ├── config.py        # config set/show
    │   ├── status.py        # status, queue commands
    │   └── utils.py         # API client wrapper, config file helpers
    ├── requirements.txt
    └── setup.py             # for `pip install -e .`
```
