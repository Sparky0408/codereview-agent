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
from app.models.repo_config import ReviewRules
from app.models.review import ReviewComment, ReviewOutput
from app.models.review_context import PRContext
from app.models.static_findings import StaticAnalysisResult

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
        self,
        pr_files: list[tuple[str, str]],
        ast_summaries: list[ASTSummary],
        review_rules: ReviewRules | None = None,
        pr_context: PRContext | None = None,
        static_findings: StaticAnalysisResult | None = None,
    ) -> ReviewOutput:
        """Analyze PR diffs and AST context to generate review comments.

        Retries once if Gemini outputs invalid JSON. On second failure,
        returns an empty ReviewOutput indicating failure rather than raising.
        """
        diffs_text = "\n\n".join(f"File: {name}\nPatch:\n{patch}" for name, patch in pr_files)
        ast_text = "\n\n".join(s.model_dump_json(indent=2) for s in ast_summaries)

        rag_text = ""
        if pr_context and pr_context.contexts_by_file:
            rag_text += "## Related Code Chunks (RAG Context)\n\n"
            for f, chunks in pr_context.contexts_by_file.items():
                if chunks:
                    rag_text += f"For file: {f}\n"
                    for chunk in chunks:
                        rag_text += (
                            f"---\nFrom {chunk.file_path} "
                            f"(similarity: {chunk.similarity_score:.2f}):\n{chunk.content}\n"
                        )
                    rag_text += "\n"

        static_text = "No tools run."
        if static_findings:
            if static_findings.findings:
                static_text = "\n".join(
                    f"- {f.file_path}:{f.line} [{f.tool}/{f.rule_id}] "
                    f"({f.severity}): {f.message}"
                    for f in static_findings.findings
                )
            else:
                static_text = "No findings (all clear!)."

        user_prompt = self._user_template.format(
            ast_summaries=ast_text,
            rag_context=rag_text,
            diffs=diffs_text,
            static_findings_block=static_text,
        )

        if review_rules:
            user_prompt += (
                f"\n\nThe team has configured these rules: "
                f"max function lines = {review_rules.max_function_lines}, "
                f"max complexity = {review_rules.max_cyclomatic_complexity}, "
                f"max function args = {review_rules.max_function_args}, "
                f"banned patterns = {review_rules.banned_patterns}. "
                f"Flag violations of these rules as CRITICAL."
            )

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
                output = ReviewOutput.model_validate_json(text)

                if review_rules:
                    severity_levels = {"NITPICK": 1, "SUGGESTION": 2, "CRITICAL": 3}
                    min_level = severity_levels.get(review_rules.severity_threshold, 1)

                    filtered_comments: list[ReviewComment] = []
                    file_counts: dict[str, int] = {}

                    for comment in output.comments:
                        level = severity_levels.get(comment.severity, 1)
                        if level < min_level:
                            continue

                        file_count = file_counts.get(comment.file_path, 0)
                        if file_count >= review_rules.max_comments_per_file:
                            continue

                        if len(filtered_comments) >= review_rules.max_total_comments:
                            break

                        filtered_comments.append(comment)
                        file_counts[comment.file_path] = file_count + 1

                    output.comments = filtered_comments

                return output

            except ValidationError as e:
                logger.error("Failed to parse Gemini output: %s", e)
                return None

        total_changed_lines = sum(patch.count("\n") + 1 for _, patch in pr_files)

        # First attempt
        output = await asyncio.to_thread(_call_gemini, user_prompt)
        if output is not None:
            if not output.comments and total_changed_lines > 50:
                logger.warning(
                    "Gemini returned 0 comments on a PR with %d changed lines",
                    total_changed_lines,
                )
            return output

        # Second attempt (fallback / retry once with strict reminder)
        logger.warning("Retrying review with strict JSON reminder...")
        retry_prompt = (
            user_prompt
            + "\n\nCRITICAL REMINDER: You MUST return strictly valid JSON matching the schema."
        )
        output_retry = await asyncio.to_thread(_call_gemini, retry_prompt)
        if output_retry is not None:
            if not output_retry.comments and total_changed_lines > 50:
                logger.warning(
                    "Gemini returned 0 comments on a PR with %d changed lines",
                    total_changed_lines,
                )
            return output_retry

        logger.error("Review completely failed after retry.")
        return ReviewOutput(summary="Review failed", comments=[])


@lru_cache
def get_reviewer() -> Reviewer:
    """Factory to create a Reviewer instance configured via Settings."""
    settings = get_settings()
    return Reviewer(api_key=settings.gemini_api_key)
