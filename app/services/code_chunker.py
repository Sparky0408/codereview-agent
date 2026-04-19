"""Service for chunking source code files."""

import hashlib
import logging

from app.models.code_chunk import CodeChunk
from app.services.ast_analyzer import ASTAnalyzer

logger = logging.getLogger(__name__)

IGNORED_DIRS = {"node_modules", ".git", "__pycache__"}
IGNORED_EXTS = {".min.js", ".lock", ".svg", ".png", ".jpg"}
MAX_FILE_LINES = 500


class CodeChunker:
    """Chunks code files into function-level and module-level chunks."""

    def __init__(self, analyzer: ASTAnalyzer) -> None:
        """Initialize the CodeChunker with an ASTAnalyzer."""
        self.analyzer = analyzer

    def _generate_chunk_id(
        self, repo_full_name: str, file_path: str, chunk_type: str, name: str
    ) -> str:
        """Generate a unique ID for a chunk."""
        raw = f"{repo_full_name}:{file_path}:{chunk_type}:{name}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _should_skip(self, file_path: str, content: str) -> bool:
        """Check if a file should be skipped based on path or size."""
        # Check ignored dirs
        parts = file_path.split("/")
        if any(d in IGNORED_DIRS for d in parts):
            return True

        # Check ignored extensions
        if any(file_path.endswith(ext) for ext in IGNORED_EXTS):
            return True

        # Check file length limit
        if content.count("\n") > MAX_FILE_LINES:
            logger.info("Skipping large file: %s", file_path)
            return True

        return False

    async def chunk_file(
        self, file_path: str, content: str, repo_full_name: str
    ) -> list[CodeChunk]:
        """Generate code chunks for a given file.

        Args:
            file_path: The file path in the repo.
            content: The file's source code.
            repo_full_name: Standard 'owner/repo' GitHub name.

        Returns:
            A list of CodeChunk objects.
        """
        if self._should_skip(file_path, content):
            return []

        summary = await self.analyzer.analyze(file_path, content)
        lines = content.split("\n")

        if summary is None or summary.language == "unknown":
            chunk_id = self._generate_chunk_id(repo_full_name, file_path, "file", "whole")
            return [
                CodeChunk(
                    chunk_id=chunk_id,
                    repo_full_name=repo_full_name,
                    file_path=file_path,
                    function_name=None,
                    start_line=1,
                    end_line=len(lines),
                    content=content,
                    language="unknown",
                )
            ]

        chunks: list[CodeChunk] = []
        covered_lines: set[int] = set()

        for i, func in enumerate(summary.functions):
            sl = max(1, func.start_line)
            el = min(len(lines), func.end_line)
            func_content = "\n".join(lines[sl - 1:el])

            func_name = func.name or "anonymous"
            chunk_id = self._generate_chunk_id(
                repo_full_name, file_path, "function", f"{func_name}_{i}"
            )

            chunks.append(
                CodeChunk(
                    chunk_id=chunk_id,
                    repo_full_name=repo_full_name,
                    file_path=file_path,
                    function_name=func_name,
                    start_line=sl,
                    end_line=el,
                    content=func_content,
                    language=summary.language,
                )
            )
            for num in range(sl, el + 1):
                covered_lines.add(num)

        # Build module-level chunk (keep lines not inside functions)
        module_content = "\n".join(
            lines[i] if (i + 1) not in covered_lines else ""
            for i in range(len(lines))
        ).strip()

        if module_content:
            chunk_id = self._generate_chunk_id(repo_full_name, file_path, "module", "module_level")
            chunks.append(
                CodeChunk(
                    chunk_id=chunk_id,
                    repo_full_name=repo_full_name,
                    file_path=file_path,
                    function_name=None,
                    start_line=1,
                    end_line=len(lines),
                    content=module_content,
                    language=summary.language,
                )
            )

        return chunks
