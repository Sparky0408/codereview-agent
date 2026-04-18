# CodeReview Agent

Open-source, self-hostable GitHub bot that performs AST-aware + RAG-augmented LLM code reviews on pull requests. Built with FastAPI, tree-sitter, ChromaDB, and Gemini 2.5 Pro. Receives PR webhooks, parses diffs with tree-sitter, retrieves related context via RAG, and posts severity-tiered inline review comments (`CRITICAL`, `SUGGESTION`, `NITPICK`).

**Status:** Weekend 1 — Skeleton scaffold. Not yet functional.
