<div align="center">

# CodeReview Agent

[![CI](https://github.com/Sparky0408/codereview-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Sparky0408/codereview-agent/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Gemini](https://img.shields.io/badge/Gemini_2.5-Pro_%2B_Flash-4285F4?logo=google&logoColor=white)](https://ai.google.dev/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](Dockerfile)

**A self-hostable GitHub App that reviews pull requests with AST context, static analysis, RAG retrieval, and structured Gemini output.**

CodeReview Agent is built for teams that want useful AI review comments without sending their workflow through a black-box SaaS. It verifies GitHub webhooks, fetches PR diffs with installation tokens, analyzes changed code, retrieves related repo context, asks Gemini for schema-validated findings, and posts severity-tiered inline comments back to GitHub.

</div>

---

## Demo

<p align="center">
  <img src="docs/assets/demo.png" alt="CodeReview Agent posting severity-tiered inline review comments on a GitHub pull request" width="860" />
</p>

## What It Does

When a pull request is opened or updated, CodeReview Agent runs a complete review pipeline:

1. Verifies the `X-Hub-Signature-256` webhook signature with HMAC-SHA256.
2. Fetches the pull request diff through a GitHub App installation token.
3. Parses changed Python, JavaScript, and TypeScript files with tree-sitter.
4. Runs static analysis with ruff, bandit, semgrep, and ESLint.
5. Retrieves related repository chunks from ChromaDB using local embeddings.
6. Sends diff, AST metadata, linter findings, and RAG context to Gemini.
7. Validates the LLM response with Pydantic before posting anything.
8. Posts inline review comments as `CRITICAL`, `SUGGESTION`, or `NITPICK`.
9. Tracks thumbs-up and thumbs-down reactions for a feedback loop.

## Why It Is Different

Most AI review bots treat code as plain text. This project gives the model the same supporting context a serious reviewer would want.

| Capability | Why it matters |
|------------|----------------|
| AST-aware review | Function boundaries, line ranges, argument counts, and complexity signals are available before prompting. |
| Static analysis fusion | Mechanical findings from linters become context, so the LLM can focus on semantic and design issues. |
| RAG over the repository | Related code chunks are retrieved from ChromaDB instead of reviewing a diff in isolation. |
| Structured output | Gemini responses are validated against Pydantic models before comments are posted. |
| GitHub App auth | Reviews run with installation tokens, not personal access tokens. |
| Self-hostable stack | FastAPI, Redis, PostgreSQL, ChromaDB, workers, and dashboard run on your infrastructure. |

## Feature Matrix

| Feature | CodeReview Agent | CodeRabbit | GitHub Copilot | PR-Agent |
|---------|:----------------:|:----------:|:--------------:|:--------:|
| Self-hostable | Yes | No | No | Yes |
| GitHub App flow | Yes | Yes | Yes | Partial |
| AST-aware diff parsing | Yes | No | No | Partial |
| RAG context retrieval | Yes | No | No | No |
| Static analysis before LLM | Yes | Partial | No | Partial |
| Feedback learning loop | Yes | Yes | No | No |
| Per-repo configuration | Yes | Yes | No | Yes |
| Open source | Yes | No | No | Yes |

## Architecture

```mermaid
flowchart LR
    A["GitHub Webhook"] --> B["FastAPI Webhook Handler"]
    B --> C["HMAC-SHA256 Verification"]
    C --> D["Redis + ARQ Queue"]
    D --> E["Review Worker"]
    E --> F["GitHub Diff Fetcher"]
    E --> G["tree-sitter AST Analyzer"]
    E --> H["Static Analysis"]
    E --> I["ChromaDB RAG Retriever"]
    F & G & H & I --> J["Gemini Structured Review"]
    J --> K["Pydantic Validation"]
    K --> L["GitHub Inline Comments"]
    L --> M["PostgreSQL Feedback Store"]
    M --> N["Streamlit Dashboard"]
```

Read the deeper design notes in [docs/architecture.md](docs/architecture.md).

## Tech Stack

| Layer | Technology |
|-------|------------|
| Web | FastAPI, uvicorn |
| Validation | Pydantic v2, pydantic-settings |
| GitHub | PyGitHub, GitHub App JWT, installation tokens |
| LLM | Gemini 2.5 Pro for review, Gemini 2.5 Flash for triage |
| AST | tree-sitter with Python, JavaScript, and TypeScript parsers |
| Static analysis | ruff, bandit, semgrep, ESLint |
| RAG | ChromaDB, `sentence-transformers/all-MiniLM-L6-v2` |
| Queue | Redis, ARQ |
| Database | PostgreSQL 16, SQLAlchemy 2.0 async, asyncpg |
| Dashboard | Streamlit, Plotly |
| Packaging | uv, hatchling |
| Containers | Docker, Docker Compose |

## Quick Start

### Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker and Docker Compose
- A GitHub App with webhook delivery enabled
- A Gemini API key

### 1. Clone and install

```bash
git clone https://github.com/Sparky0408/codereview-agent.git
cd codereview-agent
uv sync
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
GITHUB_APP_ID=123456
GITHUB_PRIVATE_KEY_PATH=secrets/codereview-agent.pem
GITHUB_WEBHOOK_SECRET=replace-with-your-webhook-secret
GEMINI_API_KEY=replace-with-your-gemini-api-key
DATABASE_URL=postgresql+asyncpg://codereview:codereview@postgres:5432/codereview
REDIS_URL=redis://redis:6379/0
```

Place your GitHub App private key at `secrets/codereview-agent.pem`. The `secrets/` directory is ignored by git.

### 3. Run the stack

```bash
docker compose up -d
```

The API runs on [http://localhost:8000](http://localhost:8000), and the dashboard runs on [http://localhost:8501](http://localhost:8501).

### 4. Connect GitHub

1. Install the GitHub App on a test repository.
2. Point the webhook URL to `/webhook` on your public tunnel or deployment URL.
3. Open or update a pull request.
4. Watch CodeReview Agent post inline review comments.

## Local Development

Run the supporting services:

```bash
docker compose up postgres redis -d
```

Run the API locally:

```bash
uv run uvicorn app.main:app --reload
```

Run checks before opening a PR:

```bash
uv run pytest -v
uv run ruff check app/ tests/ dashboard/
uv run mypy app/
```

## Per-Repo Configuration

Add `.codereview.yml` to a repository to tune review behavior:

```yaml
enabled: true
languages: [python, javascript]
ignore_paths:
  - "docs/**"
  - "*.md"
review_rules:
  max_function_lines: 50
  max_cyclomatic_complexity: 10
  max_function_args: 5
  severity_threshold: SUGGESTION
  max_comments_per_file: 10
  max_total_comments: 25
  banned_patterns:
    - "TODO"
    - "HACK"
```

See [docs/configuration.md](docs/configuration.md) for the full reference.

## Evaluation

The evaluation harness replays historical merged pull requests and compares generated comments against human review comments.

```bash
uv run python -m eval.run --repo encode/starlette --prs 5 --gemini-model gemini-2.5-flash
```

Current reports live in [`eval_reports/`](eval_reports/) when generated locally. The matching criteria are intentionally strict, so early numbers should be read as a tuning signal rather than a product-quality score.

## Project Layout

```text
app/
  webhook.py              # GitHub webhook handling and signature verification
  github_auth.py          # GitHub App JWT and installation token flow
  github_client.py        # Async wrapper around GitHub operations
  services/               # Review pipeline, AST, RAG, static analysis, posting
  workers/                # ARQ jobs
  db/                     # SQLAlchemy models and session setup
dashboard/                # Streamlit dashboard
docs/                     # Architecture and configuration docs
eval/                     # Historical PR evaluation harness
tests/                    # pytest suite mirroring app structure
```

## Roadmap

- Improve evaluation matching beyond exact-line comparison.
- Add richer dashboard slices for severity, repo, and time-window analysis.
- Tune prompt behavior using feedback reactions.
- Expand JavaScript and TypeScript static-analysis coverage.
- Harden deployment docs for production self-hosting.

## Contributing

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) for setup, test commands, branch naming, and PR expectations.

## Security

Please do not open public issues for vulnerabilities. Follow the reporting process in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)

## Author

Built by [Ruturaj](https://github.com/Sparky0408).
