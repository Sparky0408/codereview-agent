"""Service for indexing a repository into ChromaDB."""

import asyncio
import logging

import chromadb
from chromadb.api.models.Collection import Collection
from github import Auth, Github
from sentence_transformers import SentenceTransformer

from app.models.code_chunk import CodeChunk
from app.services.ast_analyzer import ASTAnalyzer
from app.services.code_chunker import CodeChunker

logger = logging.getLogger(__name__)

MAX_INDEXED_FILES = 200
BATCH_SIZE = 50


class RepoIndexer:
    """Fetches a repo, chunks its code, and indexes it via ChromaDB."""

    def __init__(self, chroma_persist_dir: str, embedding_model: str = "all-MiniLM-L6-v2") -> None:
        """Initialize the RepoIndexer."""
        self.chroma_client = chromadb.PersistentClient(path=chroma_persist_dir)
        self.model_name = embedding_model
        logger.info("Loading sentence-transformers model %s", self.model_name)
        self.embedding_model = SentenceTransformer(self.model_name)

    def _get_collection_name(self, repo_full_name: str) -> str:
        """Generate a valid ChromaDB collection name."""
        return repo_full_name.replace("/", "_")

    def _get_or_create_collection(self, repo_full_name: str) -> Collection:
        """Get or create the ChromaDB collection for the given repo."""
        name = self._get_collection_name(repo_full_name)
        return self.chroma_client.get_or_create_collection(name=name)

    def _generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Blockingly generate embeddings."""
        embeddings = self.embedding_model.encode(texts)
        return embeddings.tolist()  # type: ignore

    def _insert_chunks(self, collection: Collection, chunks: list[CodeChunk]) -> None:
        """Blockingly format and insert chunks into ChromaDB in batches."""
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i : i + BATCH_SIZE]

            ids = [c.chunk_id for c in batch]
            documents = [c.content for c in batch]
            metadatas = [
                {
                    "repo_full_name": c.repo_full_name,
                    "file_path": c.file_path,
                    "function_name": c.function_name or "",
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "language": c.language,
                }
                for c in batch
            ]

            embeddings = self._generate_embeddings(documents)

            collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,  # type: ignore
                metadatas=metadatas,  # type: ignore
            )

    async def is_indexed(self, repo_full_name: str) -> bool:
        """Check if a repository has been indexed."""
        def _check() -> bool:
            try:
                name = self._get_collection_name(repo_full_name)
                collection = self.chroma_client.get_collection(name=name)
                return collection.count() > 0
            except Exception:
                return False

        return await asyncio.to_thread(_check)

    def _fetch_repo_files(
        self, repo_full_name: str, installation_token: str, head_sha: str | None
    ) -> dict[str, str]:
        """Fetch up to MAX_INDEXED_FILES files from GitHub."""
        gh = Github(auth=Auth.Token(installation_token))
        try:
            repo = gh.get_repo(repo_full_name)
            ref = head_sha or repo.default_branch
            tree = repo.get_git_tree(ref, recursive=True)

            files = {}
            count = 0
            for el in tree.tree:
                if el.type == "blob":
                    if any(
                        d in el.path.split("/") for d in {"node_modules", ".git", "__pycache__"}
                    ):
                        continue
                    if any(
                        el.path.endswith(ext)
                        for ext in {".min.js", ".lock", ".svg", ".png", ".jpg"}
                    ):
                        continue

                    try:
                        blob = repo.get_contents(el.path, ref=ref)
                        if isinstance(blob, list):
                            continue

                        content = blob.decoded_content.decode("utf-8")
                        files[el.path] = content
                        count += 1
                        if count >= MAX_INDEXED_FILES:
                            logger.info(
                                "Reached MAX_INDEXED_FILES (%d), stopping fetch.",
                                MAX_INDEXED_FILES,
                            )
                            break
                    except Exception as e:
                        logger.warning("Failed to fetch %s: %s", el.path, e)

            return files
        finally:
            gh.close()

    def _fetch_specific_files(
        self,
        repo_full_name: str,
        changed_files: list[str],
        installation_token: str,
        head_sha: str | None,
    ) -> dict[str, str]:
        """Fetch specific files from GitHub."""
        gh = Github(auth=Auth.Token(installation_token))
        try:
            repo = gh.get_repo(repo_full_name)
            ref = head_sha or repo.default_branch

            files = {}
            for path in changed_files[:MAX_INDEXED_FILES]:
                try:
                    blob = repo.get_contents(path, ref=ref)
                    if isinstance(blob, list):
                        continue
                    content = blob.decoded_content.decode("utf-8")
                    files[path] = content
                except Exception as e:
                    logger.warning("Failed to fetch %s: %s", path, e)
            return files
        finally:
            gh.close()

    async def index_repo(
        self, repo_full_name: str, installation_token: str, head_sha: str | None = None
    ) -> int:
        """Fetch entire repo, chunk and index it."""
        files_dict = await asyncio.to_thread(
            self._fetch_repo_files, repo_full_name, installation_token, head_sha
        )

        chunker = CodeChunker(ASTAnalyzer())
        all_chunks: list[CodeChunk] = []
        for path, content in files_dict.items():
            chunks = await chunker.chunk_file(path, content, repo_full_name)
            all_chunks.extend(chunks)

        if not all_chunks:
            return 0

        def _index() -> None:
            collection = self._get_or_create_collection(repo_full_name)
            self._insert_chunks(collection, all_chunks)

        await asyncio.to_thread(_index)
        return len(all_chunks)

    async def incremental_update(
        self,
        repo_full_name: str,
        changed_files: list[str],
        installation_token: str,
        head_sha: str | None = None
    ) -> int:
        """Update the index for specific changed files."""
        files_dict = await asyncio.to_thread(
            self._fetch_specific_files, repo_full_name, changed_files, installation_token, head_sha
        )

        chunker = CodeChunker(ASTAnalyzer())

        def _delete_old() -> None:
            collection = self._get_or_create_collection(repo_full_name)
            for file_path in changed_files:
                try:
                    collection.delete(where={"file_path": file_path})
                except Exception as e:
                    logger.warning("Failed to delete chunks for %s: %s", file_path, e)

        await asyncio.to_thread(_delete_old)

        all_chunks: list[CodeChunk] = []
        for path, content in files_dict.items():
            chunks = await chunker.chunk_file(path, content, repo_full_name)
            all_chunks.extend(chunks)

        if not all_chunks:
            return 0

        def _insert() -> None:
            collection = self._get_or_create_collection(repo_full_name)
            self._insert_chunks(collection, all_chunks)

        await asyncio.to_thread(_insert)
        return len(all_chunks)
