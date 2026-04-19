"""Service for retrieving relevant code context from ChromaDB."""

import asyncio
import logging

import chromadb
from sentence_transformers import SentenceTransformer

from app.models.review_context import PRContext, RetrievedContext

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    """Estimate token count for a piece of text (roughly chars / 4)."""
    return max(1, len(text) // 4)


class ContextRetriever:
    """Retrieves relevant code chunks for pull request patches."""

    def __init__(self, chroma_persist_dir: str, embedding_model: str = "all-MiniLM-L6-v2") -> None:
        """Initialize the ContextRetriever."""
        self.chroma_client = chromadb.PersistentClient(path=chroma_persist_dir)
        self.model_name = embedding_model
        logger.info("Loading sentence-transformers model %s", self.model_name)
        self.embedding_model = SentenceTransformer(self.model_name)

    def _get_collection_name(self, repo_full_name: str) -> str:
        """Generate a valid ChromaDB collection name."""
        return repo_full_name.replace("/", "_")

    def _compute_allocations(self, demands: dict[str, int], total_budget: int) -> dict[str, int]:
        """Distribute total budget evenly, redistributing surplus."""
        allocations = {k: 0 for k in demands}
        remaining_budget = total_budget
        active_keys = list(demands.keys())

        while active_keys and remaining_budget > 0:
            share = remaining_budget // len(active_keys)
            if share == 0:
                # Give remaining budget 1 by 1
                for i in range(remaining_budget):
                    allocations[active_keys[i % len(active_keys)]] += 1
                break

            new_active = []
            for k in active_keys:
                unmet_demand = demands[k] - allocations[k]
                if unmet_demand <= share:
                    allocations[k] += unmet_demand
                    remaining_budget -= unmet_demand
                else:
                    allocations[k] += share
                    remaining_budget -= share
                    new_active.append(k)

            active_keys = new_active

        return allocations

    def _retrieve_sync(
        self, repo_full_name: str, patch_by_file: dict[str, str], token_budget: int
    ) -> PRContext:
        """Synchronously perform the retrieval logic."""
        try:
            collection_name = self._get_collection_name(repo_full_name)
            collection = self.chroma_client.get_collection(name=collection_name)
        except Exception:
            return PRContext(contexts_by_file={})

        candidates: dict[str, list[RetrievedContext]] = {}

        # We can encode all patches in a batch for efficiency
        files = list(patch_by_file.keys())
        patches = [patch_by_file[f] for f in files]

        if not files:
            return PRContext(contexts_by_file={})

        embeddings = self.embedding_model.encode(patches).tolist()

        # Query ChromaDB per file
        for f, _patch, embedding in zip(files, patches, embeddings, strict=True):
            # Exclude chunks from the same file
            results = collection.query(
                query_embeddings=[embedding],
                n_results=5,
                where={"file_path": {"$ne": f}},  # type: ignore[dict-item]
                include=["metadatas", "documents", "distances"]
            )

            file_candidates = []
            if results and results["ids"] and results["ids"][0]:
                for i in range(len(results["ids"][0])):
                    doc = results["documents"][0][i] # type: ignore
                    meta = results["metadatas"][0][i] # type: ignore
                    dist = results["distances"][0][i] # type: ignore

                    # Convert L2 distance to similarity score
                    sim_score = 1.0 / (1.0 + float(dist)) if dist is not None else 0.0

                    ctx = RetrievedContext(
                        chunk_id=results["ids"][0][i],
                        file_path=str(meta.get("file_path", "")),
                        content=str(doc),
                        similarity_score=sim_score,
                    )
                    file_candidates.append(ctx)

            candidates[f] = file_candidates

        # Apply token budget limits
        for f in candidates:
            # Sort highest similarity first
            candidates[f].sort(key=lambda x: x.similarity_score, reverse=True)

        cost_per_file = {
            f: sum(_estimate_tokens(c.content) for c in chunk_list)
            for f, chunk_list in candidates.items()
        }

        allocations = self._compute_allocations(cost_per_file, token_budget)

        final_contexts: dict[str, list[RetrievedContext]] = {}
        for f, chunk_list in candidates.items():
            kept = []
            used_tokens = 0
            for c in chunk_list:
                c_tokens = _estimate_tokens(c.content)
                if used_tokens + c_tokens <= allocations[f]:
                    kept.append(c)
                    used_tokens += c_tokens
            final_contexts[f] = kept

        return PRContext(contexts_by_file=final_contexts)

    async def retrieve_context(
        self, repo_full_name: str, patch_by_file: dict[str, str], token_budget: int = 12000
    ) -> PRContext:
        """Returns the retrieved code context."""
        return await asyncio.to_thread(
            self._retrieve_sync, repo_full_name, patch_by_file, token_budget
        )
