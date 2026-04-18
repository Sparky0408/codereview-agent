"""FastAPI entrypoint — route mounting only.

Webhook logic, LLM calls, and business logic live elsewhere.
"""

import logging

from fastapi import FastAPI

from app.config import get_settings
from app.webhook import router as webhook_router

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Open-source GitHub bot that reviews PRs using Gemini + tree-sitter + RAG.",
    version="0.1.0",
)

app.include_router(webhook_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — returns 200 with status ok."""
    return {"status": "ok"}
