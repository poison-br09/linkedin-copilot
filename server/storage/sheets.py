import json
import logging
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Column order in the shared Google Sheet
SHEET_COLUMNS = [
    "Receiver",       # Employee (system user) display name
    "Sender",         # Person in LinkedIn DM who shared the post
    "Timestamp",      # When the CEO shared the post
    "Event URN",      # LinkedIn message ID
    "Activity URN",   # LinkedIn post ID
    "Author",         # Original post author
    "Author Headline",
    "Category",
    "Title",
    "Summary",
    "Links",
    "Post URL",
]


def _build_service():
    creds = service_account.Credentials.from_service_account_file(
        settings.google_service_account_path,
        scopes=SCOPES,
    )
    return build("sheets", "v4", credentials=creds)


def ensure_header(sheet_id: Optional[str] = None) -> None:
    """Write the header row if the sheet is empty. Call once at startup."""
    sheet_id = sheet_id or settings.google_sheet_id
    try:
        svc = _build_service()
        result = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range="Sheet1!A1:A1")
            .execute()
        )
        if not result.get("values"):
            svc.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range="Sheet1!A1",
                valueInputOption="RAW",
                body={"values": [SHEET_COLUMNS]},
            ).execute()
            logger.info("Sheet header row written.")
    except HttpError as e:
        logger.error("Failed to ensure sheet header: %s", e)


def append_row(data: dict, sheet_id: Optional[str] = None) -> None:
    """
    Append one row to the shared Google Sheet.

    Expected keys in `data`:
        receiver, sender, timestamp, event_urn, activity_urn,
        author, author_headline, category, title, summary, links, post_url
    """
    sheet_id = sheet_id or settings.google_sheet_id
    links_str = ", ".join(data.get("links") or [])
    row = [
        data.get("receiver", ""),
        data.get("sender", ""),
        data.get("timestamp", ""),
        data.get("event_urn", ""),
        data.get("activity_urn", ""),
        data.get("author", ""),
        data.get("author_headline", ""),
        data.get("category", ""),
        data.get("title", ""),
        data.get("summary", ""),
        links_str,
        data.get("post_url", ""),
    ]
    try:
        svc = _build_service()
        svc.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range="Sheet1!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
        logger.info("Row appended to sheet for event_urn=%s", data.get("event_urn"))
    except HttpError as e:
        logger.error("Failed to append row to sheet: %s", e)
        raise
