"""Tests for RepoIndexer service."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.code_chunk import CodeChunk
from app.services.repo_indexer import RepoIndexer

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
    with patch("app.services.repo_indexer.SentenceTransformer") as mock_model:
        model_instance = mock_model.return_value

        # model.encode has to return something that we can convert to list
        class MockTensor:
            def tolist(self) -> list[list[float]]:
                return [[0.1, 0.2, 0.3]]

        model_instance.encode.return_value = MockTensor()
        yield model_instance


@pytest.fixture
def mock_github() -> Generator[MagicMock, None, None]:
    """Mock GitHub PyGithub Client."""
    with patch("app.services.repo_indexer.Github") as mock_gh:
        gh_instance = mock_gh.return_value
        repo_mock = MagicMock()
        gh_instance.get_repo.return_value = repo_mock

        # mock tree
        tree_mock = MagicMock()
        element = MagicMock()
        element.type = "blob"
        element.path = "test.py"
        tree_mock.tree = [element]
        repo_mock.get_git_tree.return_value = tree_mock

        # mock content
        blob_mock = MagicMock()
        blob_mock.decoded_content = b"def test(): pass"
        repo_mock.get_contents.return_value = blob_mock

        yield repo_mock


@pytest.fixture
def mock_chunker() -> Generator[MagicMock, None, None]:
    """Mock CodeChunker."""
    with patch("app.services.repo_indexer.CodeChunker") as mock_class:
        chunker_instance = mock_class.return_value
        chunker_instance.chunk_file = AsyncMock(return_value=[
            CodeChunk(
                chunk_id="123",
                repo_full_name="owner/repo",
                file_path="test.py",
                function_name="test",
                start_line=1,
                end_line=2,
                content="def test(): pass",
                language="python"
            )
        ])
        yield chunker_instance


@pytest.fixture
def repo_indexer(mock_chroma: MagicMock, mock_embeddings: MagicMock) -> RepoIndexer:
    """Instantiate RepoIndexer with mostly mocked components."""
    return RepoIndexer("/tmp/chroma")


async def test_is_indexed_true(repo_indexer: RepoIndexer, mock_chroma: MagicMock) -> None:
    collection_mock = mock_chroma.get_collection.return_value
    collection_mock.count.return_value = 5
    assert await repo_indexer.is_indexed("owner/repo") is True


async def test_is_indexed_false(repo_indexer: RepoIndexer, mock_chroma: MagicMock) -> None:
    mock_chroma.get_collection.side_effect = Exception("Not found")
    assert await repo_indexer.is_indexed("owner/repo") is False


async def test_index_repo(
    repo_indexer: RepoIndexer,
    mock_chroma: MagicMock,
    mock_embeddings: MagicMock,
    mock_github: MagicMock,
    mock_chunker: MagicMock
) -> None:
    chunks_count = await repo_indexer.index_repo("owner/repo", "token")
    assert chunks_count == 1

    # Verify chroma insertion
    collection_mock = mock_chroma.get_or_create_collection.return_value
    collection_mock.upsert.assert_called_once()
    kwargs = collection_mock.upsert.call_args.kwargs
    assert kwargs["ids"] == ["123"]
    assert kwargs["documents"] == ["def test(): pass"]
    assert kwargs["metadatas"][0]["language"] == "python"

    # Verify embeddings called
    mock_embeddings.encode.assert_called_once()


async def test_incremental_update(
    repo_indexer: RepoIndexer,
    mock_chroma: MagicMock,
    mock_embeddings: MagicMock,
    mock_github: MagicMock,
    mock_chunker: MagicMock
) -> None:
    chunks_count = await repo_indexer.incremental_update("owner/repo", ["test.py"], "token")
    assert chunks_count == 1

    collection_mock = mock_chroma.get_or_create_collection.return_value
    # Verify deletion of old chunks
    collection_mock.delete.assert_called_once_with(where={"file_path": "test.py"})
    # Verify new chunks upserted
    collection_mock.upsert.assert_called_once()
