"""Model for chunked code."""

from pydantic import BaseModel


class CodeChunk(BaseModel):
    """Represents a chunk of code extracted from a file."""

    chunk_id: str
    repo_full_name: str
    file_path: str
    function_name: str | None
    start_line: int
    end_line: int
    content: str
    language: str
