"""Models for context retrieval during code review."""

from pydantic import BaseModel, ConfigDict


class RetrievedContext(BaseModel):
    """Represents a code chunk relevant to a patch."""

    chunk_id: str
    file_path: str
    content: str
    similarity_score: float

    model_config = ConfigDict(frozen=True)


class PRContext(BaseModel):
    """Contexts maps a patched file path to a list of retrieved chunks."""

    contexts_by_file: dict[str, list[RetrievedContext]]

    def total_chunks(self) -> int:
        """Return the total number of chunks across all files."""
        return sum(len(chunks) for chunks in self.contexts_by_file.values())
