"""
NVIDIA Nemotron summarizer.

Calls the Nemotron API (OpenAI-compatible) and returns structured JSON
with title, summary, category, main_topic, and extracted links.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from openai import OpenAI, RateLimitError, APIError

from config import settings

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (Path(__file__).parent.parent / "prompts" / "summary_prompt.txt").read_text()


def _get_client(api_key: Optional[str] = None) -> OpenAI:
    return OpenAI(
        api_key=api_key or settings.nvidia_api_key,
        base_url=settings.nvidia_base_url,
    )


def summarize(raw_data: dict, api_key: Optional[str] = None) -> dict:
    """
    Summarize a LinkedIn post using Nemotron.

    Args:
        raw_data: The raw scraped post dict from the queue.
        api_key: Per-user NVIDIA API key (falls back to global key).

    Returns:
        Dict with keys: title, summary, category, main_topic, links.

    Raises:
        RateLimitError: Propagated so the caller can mark the row as FAILED.
        ValueError: If the LLM returns unparseable JSON.
    """
    post_content = _build_post_content(raw_data)
    prompt = _PROMPT_TEMPLATE.format(post_content=post_content)

    client = _get_client(api_key)

    try:
        response = client.chat.completions.create(
            model=settings.nvidia_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=512,
        )
    except RateLimitError:
        logger.warning("Nemotron rate limit hit for event_urn=%s", raw_data.get("event_urn"))
        raise

    content = response.choices[0].message.content.strip()
    return _parse_response(content, raw_data)


def _build_post_content(raw_data: dict) -> str:
    parts = []
    if raw_data.get("author"):
        parts.append(f"Author: {raw_data['author']}")
    if raw_data.get("author_headline"):
        parts.append(f"Headline: {raw_data['author_headline']}")
    if raw_data.get("post_body"):
        parts.append(f"\nPost:\n{raw_data['post_body']}")
    if raw_data.get("urls"):
        parts.append(f"\nURLs mentioned: {', '.join(raw_data['urls'])}")
    return "\n".join(parts)


def _parse_response(content: str, raw_data: dict) -> dict:
    # Strip markdown code fences if present
    clean = re.sub(r"^```(?:json)?\s*", "", content, flags=re.MULTILINE)
    clean = re.sub(r"\s*```$", "", clean, flags=re.MULTILINE).strip()

    try:
        result = json.loads(clean)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Nemotron response as JSON: %s\nRaw: %s", e, content)
        raise ValueError(f"Invalid JSON from LLM: {e}") from e

    # Merge scraped URLs with LLM-extracted links
    scraped_urls = set(raw_data.get("urls") or [])
    llm_links = set(result.get("links") or [])
    result["links"] = list(scraped_urls | llm_links)

    return {
        "title": result.get("title", ""),
        "summary": result.get("summary", ""),
        "category": result.get("category", "General"),
        "main_topic": result.get("main_topic", ""),
        "links": result.get("links", []),
    }
