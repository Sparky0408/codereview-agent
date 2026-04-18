"""LLM-based code review engine using Gemini."""

import asyncio
import logging
from functools import lru_cache
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import ValidationError

from app.config import get_settings
from app.models.ast_summary import ASTSummary
from app.models.review import ReviewOutput

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent / "prompts"


class Reviewer:
    """Generates structured code reviews using Gemini's structured output."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-pro") -> None:
        """Initialise the Reviewer with Gemini client and pre-load prompts."""
        self.model = model
        self.client = genai.Client(api_key=api_key)

        system_file = _PROMPT_DIR / "review_system.md"
        user_file = _PROMPT_DIR / "review_user.md"
        self._system_prompt = system_file.read_text("utf-8") if system_file.exists() else ""
        self._user_template = user_file.read_text("utf-8") if user_file.exists() else ""

    async def review(
        self, pr_files: list[tuple[str, str]], ast_summaries: list[ASTSummary]
    ) -> ReviewOutput:
        """Analyze PR diffs and AST context to generate review comments.

        Retries once if Gemini outputs invalid JSON. On second failure,
        returns an empty ReviewOutput indicating failure rather than raising.
        """
        diffs_text = "\n\n".join(f"File: {name}\nPatch:\n{patch}" for name, patch in pr_files)
        ast_text = "\n\n".join(s.model_dump_json(indent=2) for s in ast_summaries)

        user_prompt = self._user_template.format(ast_summaries=ast_text, diffs=diffs_text)

        config = types.GenerateContentConfig(
            system_instruction=self._system_prompt,
            response_mime_type="application/json",
            response_schema=ReviewOutput,
            temperature=0.0,
        )

        def _call_gemini(prompt: str) -> ReviewOutput | None:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )

            if response.usage_metadata:
                usage = response.usage_metadata
                logger.info(
                    "Gemini token usage - Total: %s (Prompt: %s, Candidates: %s)",
                    usage.total_token_count,
                    usage.prompt_token_count,
                    usage.candidates_token_count,
                )

            text = response.text
            if not text:
                return None

            try:
                return ReviewOutput.model_validate_json(text)
            except ValidationError as e:
                logger.error("Failed to parse Gemini output: %s", e)
                return None

        # First attempt
        output = await asyncio.to_thread(_call_gemini, user_prompt)
        if output is not None:
            return output

        # Second attempt (fallback / retry once with strict reminder)
        logger.warning("Retrying review with strict JSON reminder...")
        retry_prompt = (
            user_prompt
            + "\n\nCRITICAL REMINDER: You MUST return strictly valid JSON matching the schema."
        )
        output_retry = await asyncio.to_thread(_call_gemini, retry_prompt)
        if output_retry is not None:
            return output_retry

        logger.error("Review completely failed after retry.")
        return ReviewOutput(summary="Review failed", comments=[])


@lru_cache
def get_reviewer() -> Reviewer:
    """Factory to create a Reviewer instance configured via Settings."""
    settings = get_settings()
    return Reviewer(api_key=settings.gemini_api_key)
