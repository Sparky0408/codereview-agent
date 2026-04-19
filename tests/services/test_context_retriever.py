"""Tests for ContextRetriever service."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from app.services.context_retriever import ContextRetriever, _estimate_tokens

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_chroma() -> Generator[MagicMock, None, None]:
    """Mock ChromaDB PersistentClient."""
    with patch("chromadb.PersistentClient") as mock_client:
        client_instance = mock_client.return_value
        collection_mock = MagicMock()
        client_instance.get_or_create_collection.return_value = collection_mock
        client_instance.get_collection.return_value = collection_mock
        yield client_instance


@pytest.fixture
def mock_embeddings() -> Generator[MagicMock, None, None]:
    """Mock SentenceTransformer."""
    with patch("app.services.context_retriever.SentenceTransformer") as mock_model:
        model_instance = mock_model.return_value

        class MockTensor:
            def tolist(self) -> list[list[float]]:
                return [[0.1, 0.2, 0.3]]

        model_instance.encode.return_value = MockTensor()
        yield model_instance


@pytest.fixture
def context_retriever(mock_chroma: MagicMock, mock_embeddings: MagicMock) -> ContextRetriever:
    """Instantiate ContextRetriever with mocked components."""
    return ContextRetriever("/tmp/chroma")


async def test_empty_collection(
    context_retriever: ContextRetriever, mock_chroma: MagicMock
) -> None:
    """Test when the ChromaDB collection does not exist."""
    mock_chroma.get_collection.side_effect = Exception("Collection not found")
    pr_context = await context_retriever.retrieve_context("owner/repo", {"file1.py": "patch"})
    assert pr_context.contexts_by_file == {}


async def test_happy_path(
    context_retriever: ContextRetriever, mock_chroma: MagicMock, mock_embeddings: MagicMock
) -> None:
    """Test full retrieval with no budget limits hit."""
    collection_mock = mock_chroma.get_collection.return_value
    collection_mock.query.return_value = {
        "ids": [["c1", "c2"]],
        "documents": [["def foo(): pass", "def bar(): pass"]],
        "metadatas": [[{"file_path": "other1.py"}, {"file_path": "other2.py"}]],
        "distances": [[0.1, 0.2]]
    }

    patches = {"test.py": "def new_patch(): pass"}
    pr_context = await context_retriever.retrieve_context("owner/repo", patches)

    assert "test.py" in pr_context.contexts_by_file
    candidates = pr_context.contexts_by_file["test.py"]
    assert len(candidates) == 2
    assert candidates[0].chunk_id == "c1"
    assert candidates[1].chunk_id == "c2"
    # Verify same-file exclusion was added to query
    collection_mock.query.assert_called_once()
    kwargs = collection_mock.query.call_args.kwargs
    assert kwargs["where"] == {"file_path": {"$ne": "test.py"}}


async def test_budget_limits_and_drop_lowest_similarity(
    context_retriever: ContextRetriever, mock_chroma: MagicMock
) -> None:
    """Test that lowest similarity chunks are dropped when budget is exceeded."""
    collection_mock = mock_chroma.get_collection.return_value

    # 4 chunks, each about 20 chars long -> 5 tokens. Total 20 tokens.
    # If budget is 15 tokens, we should keep 3 chunks.
    collection_mock.query.return_value = {
        "ids": [["c1", "c2", "c3", "c4"]],
        "documents": [[
            "def a(): pass       ", "def b(): pass       ",
            "def c(): pass       ", "def d(): pass       "
        ]],
        "metadatas": [[{"file_path": "other.py"}] * 4],
        "distances": [[0.1, 0.4, 0.2, 0.3]] # c1 (0.1) is most similar, c4 (0.4) is least similar
    }

    # A 20 length string has 5 tokens in our heuristic.
    assert _estimate_tokens("def a(): pass       ") == 5

    patches = {"test.py": "patch"}
    pr_context = await context_retriever.retrieve_context(
        "owner/repo", patches, token_budget=15
    )

    candidates = pr_context.contexts_by_file["test.py"]
    assert len(candidates) == 3
    # order should be c1, c3, c4 (distances: 0.1, 0.2, 0.3)
    assert [c.chunk_id for c in candidates] == ["c1", "c3", "c4"]


async def test_budget_redistribution(
    context_retriever: ContextRetriever, mock_chroma: MagicMock, mock_embeddings: MagicMock
) -> None:
    """Test that surplus budget from one file is given to another."""
    collection_mock = mock_chroma.get_collection.return_value

    class MockTensor:
        def tolist(self) -> list[list[float]]:
            return [[0.1], [0.2]]
    mock_embeddings.encode.return_value = MockTensor()

    def side_effect(*args: any, **kwargs: any) -> dict:  # type: ignore
        # If test1.py, return 1 small chunk (e.g. 5 tokens)
        # If test2.py, return many chunks (e.g. 30 tokens total)
        if kwargs["where"] == {"file_path": {"$ne": "test1.py"}}:
            return {
                "ids": [["c1"]],
                "documents": [["def a(): pass       "]], # 5 tokens
                "metadatas": [[{"file_path": "other.py"}]],
                "distances": [[0.1]]
            }
        else:
            return {
                "ids": [["d1", "d2", "d3", "d4", "d5", "d6"]],
                "documents": [["def b(): pass       "] * 6], # 5 tokens each, total 30
                "metadatas": [[{"file_path": "other.py"}] * 6],
                "distances": [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6]]
            }

    collection_mock.query.side_effect = side_effect

    # 2 files, so equal budget is 15 each. Total budget 30.
    # test1.py uses 5 tokens, surplus is 10.
    # test2.py can use up to 15 + 10 = 25 tokens. 25 tokens / 5 = 5 chunks.
    pr_context = await context_retriever.retrieve_context(
        "owner/repo",
        {"test1.py": "patch1", "test2.py": "patch2"},
        token_budget=30
    )

    assert len(pr_context.contexts_by_file["test1.py"]) == 1
    assert len(pr_context.contexts_by_file["test2.py"]) == 5
