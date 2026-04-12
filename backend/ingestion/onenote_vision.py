"""Phase 19 — GPT-4.1 Vision for OneNote Image OCR.

Calls the OpenAI vision API to describe / OCR images extracted from
OneNote pages during ingestion.

Configuration
-------------
The OpenAI API key is read from environment variables in this order:

1. ``OPENAI_API_KEY``   (standard OpenAI SDK variable)
2. ``KTS_OPENAI_API_KEY``   (KTS-specific override)
3. ``AZURE_OPENAI_API_KEY`` + ``AZURE_OPENAI_ENDPOINT``  (Azure OpenAI)

If no key is found the module raises ``VisionConfigError`` when
``describe_image()`` is first called.  Pass ``skip_on_error=True`` to
suppress the exception and return an empty description instead (useful
for local testing without API credentials).

Model
-----
Defaults to ``gpt-4.1`` (free-tier eligible in your org).
Can be overridden via the ``model`` parameter or the
``KTS_VISION_MODEL`` environment variable.

Usage
-----
    from backend.ingestion.onenote_vision import describe_image

    description = describe_image(
        image_bytes=my_png_bytes,
        fmt="png",
        page_title="Filemask Legend",
        section_name="Tech Tips",
    )
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-4.1"
_DEFAULT_MAX_TOKENS = 512

_SYSTEM_PROMPT = (
    "You are an expert document analyst helping to build a searchable "
    "knowledge base from OneNote pages. Your task is to describe images "
    "extracted from these pages so their content becomes searchable text.\n\n"
    "For each image:\n"
    "1. Extract ALL visible text (exact wording matters — people will search for it).\n"
    "2. Describe what the image shows: screenshots, diagrams, charts, tables, etc.\n"
    "3. If it is a screenshot of a software UI, name the application and describe "
    "the user action or setting being shown.\n"
    "4. If it contains a table or structured data, reproduce the data in plain text.\n"
    "5. Be specific and complete. Do not summarise or paraphrase text — transcribe it.\n"
    "6. Output plain prose followed by any transcribed text in a 'Text found:' section."
)


class VisionConfigError(RuntimeError):
    """Raised when no OpenAI API key is available."""


def describe_image(
    image_bytes: bytes,
    fmt: str = "jpeg",
    page_title: str = "",
    section_name: str = "",
    model: Optional[str] = None,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
    skip_on_error: bool = False,
) -> str:
    """Call GPT-4.1 vision to get a text description of *image_bytes*.

    Parameters
    ----------
    image_bytes : bytes
        Raw image data (JPEG, PNG, or GIF).
    fmt : str
        Image format string: "jpeg", "png", or "gif".
    page_title : str
        Title of the OneNote page containing this image (injected as context).
    section_name : str
        Section name (injected as context).
    model : str | None
        Override the default model (``gpt-4.1``).
    max_tokens : int
        Maximum tokens in the completion.
    skip_on_error : bool
        If True, return "" on any error instead of raising.

    Returns
    -------
    str
        Text description of the image content.
    """
    resolved_model = model or os.environ.get("KTS_VISION_MODEL", _DEFAULT_MODEL)

    try:
        client = _get_client()
    except VisionConfigError:
        if skip_on_error:
            logger.warning("[Phase19] No OpenAI API key — skipping image OCR")
            return ""
        raise

    b64 = base64.b64encode(image_bytes).decode("ascii")
    mime = _mime_type(fmt)
    data_url = f"data:{mime};base64,{b64}"

    context_note = ""
    if section_name or page_title:
        parts = []
        if section_name:
            parts.append(f"Section: {section_name}")
        if page_title:
            parts.append(f"Page: {page_title}")
        context_note = "Context — " + " | ".join(parts) + "\n\n"

    user_content = [
        {
            "type": "text",
            "text": (
                f"{context_note}"
                "Describe this image extracted from a OneNote page. "
                "Extract all text and explain what the image shows."
            ),
        },
        {
            "type": "image_url",
            "image_url": {"url": data_url, "detail": "high"},
        },
    ]

    try:
        response = client.chat.completions.create(
            model=resolved_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
            ],
            max_tokens=max_tokens,
            temperature=0.1,   # Low temperature for factual transcription
        )
        text = response.choices[0].message.content or ""
        logger.debug(
            "[Phase19] Vision response for page '%s': %d chars", page_title, len(text)
        )
        return text.strip()

    except Exception as exc:
        if skip_on_error:
            logger.warning("[Phase19] Vision call failed for '%s': %s", page_title, exc)
            return ""
        raise


def describe_images_for_page(
    images: list,  # list[OneNoteImage]
    page_title: str,
    section_name: str,
    model: Optional[str] = None,
    skip_on_error: bool = True,
) -> list[str]:
    """Describe all images on a page, returning one description string per image.

    Images that fail are returned as "" (with a warning log) rather than
    aborting the entire page ingestion.

    Parameters
    ----------
    images : list[OneNoteImage]
    page_title : str
    section_name : str
    model : str | None
    skip_on_error : bool
        Default True — a single vision failure does not abort ingestion.

    Returns
    -------
    list[str]
        One description per image.  Same length as *images*.
    """
    descriptions: list[str] = []
    for i, img in enumerate(images):
        logger.info(
            "[Phase19] Vision OCR: section='%s' page='%s' image %d/%d (%s, %d bytes)",
            section_name, page_title, i + 1, len(images), img.fmt, len(img.image_bytes),
        )
        desc = describe_image(
            image_bytes=img.image_bytes,
            fmt=img.fmt,
            page_title=page_title,
            section_name=section_name,
            model=model,
            skip_on_error=skip_on_error,
        )
        descriptions.append(desc)
    return descriptions


# ── Client factory ─────────────────────────────────────────────────────────

_client = None


def _get_client():
    """Return a cached OpenAI client, initialising it on first call."""
    global _client
    if _client is not None:
        return _client

    # Standard OpenAI
    api_key = (
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("KTS_OPENAI_API_KEY")
    )
    azure_key      = os.environ.get("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")

    try:
        import openai
    except ImportError as exc:
        raise VisionConfigError(
            "openai package is not installed. "
            "Run: pip install openai>=1.0.0"
        ) from exc

    if api_key:
        _client = openai.OpenAI(api_key=api_key)
        logger.info("[Phase19] OpenAI client initialised (standard key)")
    elif azure_key and azure_endpoint:
        _client = openai.AzureOpenAI(
            api_key=azure_key,
            azure_endpoint=azure_endpoint,
            api_version="2024-12-01-preview",
        )
        logger.info("[Phase19] OpenAI client initialised (Azure endpoint)")
    else:
        raise VisionConfigError(
            "No OpenAI API key found.  Set OPENAI_API_KEY or KTS_OPENAI_API_KEY "
            "environment variable before running OneNote ingestion with image OCR.\n"
            "Use --skip-images to ingest without image OCR."
        )

    return _client


def reset_client() -> None:
    """Force re-initialisation of the client (useful in tests)."""
    global _client
    _client = None


def _mime_type(fmt: str) -> str:
    return {
        "jpeg": "image/jpeg",
        "jpg":  "image/jpeg",
        "png":  "image/png",
        "gif":  "image/gif",
    }.get(fmt.lower(), "image/jpeg")
