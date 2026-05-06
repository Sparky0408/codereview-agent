<div align="center">

# CodeReview Agent

**Self-hostable GitHub App that reviews pull requests with AST context, static analysis, RAG retrieval, and schema-validated Gemini output.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Gemini 2.5](https://img.shields.io/badge/Gemini_2.5-Pro_%2B_Flash-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](Dockerfile)

[Quickstart](#quickstart) · [How it works](#how-it-works) · [Evaluation](#evaluation) · [Configuration](#configuration) · [Architecture](docs/architecture.md)

<img src="docs/assets/demo.png" alt="CodeReview Agent posting severity-tiered inline review comments on a GitHub pull request" width="860" />

</div>

---

> **Status — in active development.**
> The included evaluation harness scores around **P ≈ 14%, R ≈ 4%, F1 ≈ 5–6%** on `pallets/click` and `pallets/jinja` (15 PRs, `gemini-2.5-flash`). Useful as a pre-merge sanity layer today; not a replacement for human review. See [Evaluation](#evaluation) for the full numbers and known limits.

## Why this exists

Most AI review bots treat code as plain text. CodeReview Agent gives the model the supporting context a serious reviewer would want — function-level AST metadata, static-analysis findings, and related-code chunks retrieved via local embeddings — and validates the LLM's response against a Pydantic schema before any comment is posted. It runs entirely on your infrastructure with your GitHub App credentials, no third-party SaaS in the loop.

## Quickstart

**Prerequisites**: Python 3.12 with [uv](https://docs.astral.sh/uv/), Docker + Docker Compose, a GitHub App (webhook delivery enabled), a Gemini API key.

```bash
git clone https://github.com/Sparky0408/codereview-agent.git
cd codereview-agent
```

Create a `.env` file in the project root:

```env
GITHUB_APP_ID=123456
GITHUB_PRIVATE_KEY_PATH=secrets/codereview-agent.pem
GITHUB_WEBHOOK_SECRET=replace-with-your-webhook-secret
GEMINI_API_KEY=replace-with-your-gemini-api-key
DATABASE_URL=postgresql+asyncpg://codereview:codereview@postgres:5432/codereview
REDIS_URL=redis://redis:6379/0
```

Drop your GitHub App private key at `secrets/codereview-agent.pem` (the directory is git-ignored), then:

```bash
docker compose up -d
```

| Service | URL |
|---|---|
| API | <http://localhost:8000> |
| Dashboard | <http://localhost:8501> |

Install the App on a test repo, point its webhook URL at `/webhook` on your public tunnel, open a PR, and watch the comments land.

<details>
<summary><b>Local development without Docker</b></summary>

```bash
uv sync
docker compose up postgres redis -d
uv run uvicorn app.main:app --reload
```

Pre-PR checks:

```bash
uv run pytest -v
uv run ruff check app/ tests/ dashboard/
uv run mypy app/
```

</details>

## How it works

```mermaid
flowchart LR
    A["GitHub Webhook"] --> B["FastAPI handler<br/>HMAC-SHA256 verify"]
    B --> C["Redis + ARQ Queue"]
    C --> D["Review Worker"]
    D --> E["Diff fetch"]
    D --> F["tree-sitter AST"]
    D --> G["Static analysis<br/>ruff · bandit · semgrep · ESLint"]
    D --> H["ChromaDB RAG"]
    E & F & G & H --> I["Gemini 2.5"]
    I --> J["Pydantic validation"]
    J --> K["Inline comments<br/>CRITICAL · SUGGESTION · NITPICK"]
    K --> L["PostgreSQL feedback store"]
    L --> M["Streamlit dashboard"]
```

The pipeline, in order:

1. Verify the `X-Hub-Signature-256` webhook with HMAC-SHA256.
2. Fetch the PR diff via a GitHub App installation token.
3. Parse changed Python / JavaScript / TypeScript files with tree-sitter.
4. Run ruff, bandit, semgrep, and ESLint over the changed files.
5. Retrieve related repo chunks from ChromaDB (`sentence-transformers/all-MiniLM-L6-v2`).
6. Send diff + AST summaries + linter findings + RAG context to Gemini 2.5.
7. Parse the response against a Pydantic schema; retry once on malformed JSON, fail closed otherwise.
8. Apply per-repo severity threshold and per-file / total comment caps from `.codereview.yml`.
9. Post inline comments as `CRITICAL`, `SUGGESTION`, or `NITPICK`, then store reactions for the feedback loop.

Deeper notes in [docs/architecture.md](docs/architecture.md).

## Evaluation

A historical-PR replay harness lives in [`eval/`](eval/). It re-runs the pipeline against merged pull requests, then fuzz-matches the bot's comments against the original human review comments. Reports go to [`eval_reports/`](eval_reports/).

Latest runs (15 PRs each, `gemini-2.5-flash`):

| Repo | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| `pallets/click` <sub>(mean of 4 runs)</sub> | 2.0 ± 1.0 | 12.0 ± 1.4 | 66.0 ± 1.0 | **14.0% ± 6.1** | **3.0% ± 1.5** | **4.8% ± 2.4** |
| `pallets/jinja` <sub>(1 run)</sub> | 3 | 18 | 70 | **14.3%** | **4.1%** | **6.4%** |

Run it yourself:

```bash
uv run python -m eval.run \
  --repo pallets/click \
  --prs 15 \
  --gemini-model gemini-2.5-flash \
  --output eval_reports/click_15.md
```

**Caveats** to read with the numbers:

- Matching is intentionally strict — same file, ±5 lines, ≥2 shared significant words after stop-word filtering and identifier-aware tokenization (so `typing.Any` splits into `{typing, any}`).
- The bot can be technically correct and still score 0 if the historical reviewer happened not to flag that exact line.
- Repeated runs with `temperature=0` show meaningful variance (F1 ranged 2.4–7.2% on the same 15 click PRs across 4 runs). Treat single-run numbers as point estimates, not benchmarks.

## Configuration

Drop a `.codereview.yml` into a repository to tune review behavior:

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

Full reference in [docs/configuration.md](docs/configuration.md).

## Compared to other AI reviewers

| Capability | CodeReview Agent | CodeRabbit | GitHub Copilot | PR-Agent |
|---|:---:|:---:|:---:|:---:|
| Self-hostable | ✓ | – | – | ✓ |
| GitHub App auth | ✓ | ✓ | ✓ | partial |
| AST-aware diff parsing | ✓ | – | – | partial |
| RAG over the repository | ✓ | – | – | – |
| Static analysis fed to LLM | ✓ | partial | – | partial |
| Schema-validated LLM output | ✓ | – | – | – |
| Per-repo configuration | ✓ | ✓ | – | ✓ |
| Reaction-based feedback loop | ✓ | ✓ | – | – |
| Open source | ✓ | – | – | ✓ |

## Tech stack

<details>
<summary>Full stack</summary>

| Layer | Technology |
|---|---|
| Web | FastAPI, uvicorn |
| Validation | Pydantic v2, pydantic-settings |
| GitHub | PyGitHub, GitHub App JWT, installation tokens |
| LLM | Gemini 2.5 Pro (production review), Gemini 2.5 Flash (triage + eval) |
| AST | tree-sitter (Python, JavaScript, TypeScript) |
| Static analysis | ruff, bandit, semgrep, ESLint |
| RAG | ChromaDB + `sentence-transformers/all-MiniLM-L6-v2` |
| Queue | Redis, ARQ |
| Database | PostgreSQL 16, SQLAlchemy 2.0 async, asyncpg |
| Dashboard | Streamlit, Plotly |
| Packaging | uv, hatchling |
| Containers | Docker, Docker Compose |

</details>

## Project layout

<details>
<summary>Repository structure</summary>

```text
app/
  webhook.py               # GitHub webhook handling + signature verification
  github_auth.py           # GitHub App JWT + installation token flow
  github_client.py         # Async GitHub wrapper
  services/                # Review pipeline, AST, RAG, static analysis, posting
  workers/                 # ARQ jobs
  db/                      # SQLAlchemy models and session setup
  models/                  # Pydantic schemas
dashboard/                 # Streamlit dashboard (overview, feedback, eval pages)
docs/                      # Architecture and configuration docs
eval/                      # Historical PR evaluation harness
tests/                     # pytest suite mirroring app/
```

</details>

## Roadmap

- [ ] Lift evaluation precision and recall closer to human-grade signal
- [ ] Multi-run evaluation averaging to dampen LLM variance
- [ ] Richer dashboard slices for severity, repo, and time window
- [ ] Tune prompts against the feedback-reaction signal
- [ ] Expand JavaScript and TypeScript static-analysis coverage
- [ ] Production deployment recipe (TLS, key rotation, observability)

## Contributing

Contributions welcome — start with [CONTRIBUTING.md](CONTRIBUTING.md) for setup, test commands, branch naming, and PR expectations.

## Security

Please do not open public issues for vulnerabilities. Follow the reporting process in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)

## Author

Built by [Ruturaj](https://github.com/Sparky0408).
