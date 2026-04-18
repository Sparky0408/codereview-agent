# AGENTS.md — CodeReview Agent

> This file is loaded by Antigravity (and any cross-tool compatible agent) at the start of every session. It defines hard rules for this repo. **Treat these rules as non-negotiable unless I explicitly override them in a prompt.**

---

## 1. Project context

**What this is:** Open-source, self-hostable GitHub bot that performs AST + RAG-aware LLM code reviews on pull requests. Python + JavaScript/TypeScript support. Target: top-10% portfolio project for 15LPA+ SDE/ML Engineer roles.

**What it does on a PR:**
1. Receives `pull_request` webhook (opened/synchronize).
2. Verifies HMAC signature, fetches the diff using a GitHub App installation token.
3. Parses changed files via tree-sitter, runs linters (ruff/eslint/bandit/semgrep).
4. Retrieves related files via ChromaDB RAG over the indexed repo.
5. Sends everything to Gemini with a structured JSON schema.
6. Posts severity-tiered inline review comments (`CRITICAL`, `SUGGESTION`, `NITPICK`).
7. Captures 👍/👎 reactions for a learning feedback loop.

---

## 2. Tech stack (authoritative — do NOT substitute)

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.12 | No 3.13 until all deps support it |
| Web | FastAPI + uvicorn | **Never suggest Flask.** |
| Validation | Pydantic v2 | All webhook payloads + LLM outputs |
| HTTP client | httpx (async) | Not `requests`. Not `urllib`. |
| GitHub | PyGitHub + GitHub App (JWT → installation token) | Not PAT |
| LLM | Gemini 2.5 Pro (primary), 2.5 Flash (triage) | via `google-genai` SDK |
| AST | tree-sitter (Python + JavaScript/TypeScript parsers) | `ast` stdlib only as Python-specific fallback |
| Static analysis | ruff (py), ESLint (js/ts), bandit (py security), semgrep (multi-lang) | Run pre-LLM, feed output as context |
| RAG | ChromaDB (local) + `sentence-transformers/all-MiniLM-L6-v2` | No Pinecone/Weaviate |
| Queue | Redis + ARQ | Not Celery |
| DB | PostgreSQL 16 + SQLAlchemy 2.0 async + Alembic | asyncpg driver |
| Dashboard | Streamlit | Not Next.js. Not Flask templates. |
| Packaging | uv (pyproject.toml, hatchling backend) | Not poetry. Not pip-tools. |
| Containers | Docker + docker-compose | |
| CI | GitHub Actions | |

**Before adding ANY new dependency, stop and ask me.** Exceptions: test-only deps (respx, freezegun) are fine to add to dev-deps without asking.

---

## 3. Code quality rules

- **Type hints required** on every function, method, and class attribute. `Any` is a code smell — justify it in a comment.
- **Async for all I/O.** Sync I/O in async paths = bug. Wrap sync libraries (like PyGitHub) with `asyncio.to_thread`.
- **Cyclomatic complexity < 10** per function. Split if bigger.
- **Files < 300 lines.** If approaching the limit, propose a module split before adding more.
- **No `print()` statements** in `app/**`. Use the `logging` module via `logger = logging.getLogger(__name__)`.
- **No bare `except:` or `except Exception:` without re-raising or logging.**
- **Constants live in `app/constants.py`** — no magic numbers or strings in logic.
- **Docstrings on all public functions** (Google style).

---

## 4. Testing rules

- Framework: **pytest + pytest-asyncio**. Test files in `tests/`, mirror the `app/` tree.
- **Never make live API calls in tests.** Mock GitHub via `respx`, mock Gemini with explicit stub responses.
- **Every new public function needs at least one test.** Cover: happy path + one failure mode at minimum.
- Use fixtures in `tests/conftest.py` for shared setup (test DB, mock GitHub client).
- Run `uv run pytest -v` before reporting a task done. **If tests fail, the task is not done.**
- Coverage target: 80%+ on new code (`uv run pytest --cov=app`).

---

## 5. Security rules (enforced strictly)

- **Never hardcode secrets.** All credentials come from `app/config.py` Settings, backed by env vars.
- `.env` is in `.gitignore`. `.env.example` must be updated when a new env var is added.
- **Never log secrets** — no logging of tokens, JWT strings, webhook payloads that may contain sensitive data.
- **Webhook signature verification is mandatory.** HMAC-SHA256 against `X-Hub-Signature-256`. A webhook route without this check is a bug.
- **Never commit** the GitHub App private key PEM. It lives in `secrets/` which is gitignored.
- Bandit findings on our own code must be zero before merge.

---

## 6. Agent behavior rules (saves my tokens)

These are the single most important rules in this file. Violating them wastes my Antigravity quota.

- **SCOPE:** Do not modify files I did not mention. If you think an adjacent file needs changing, ask — do not edit preemptively.
- **NO UNSOLICITED REFACTORS.** If you see something you'd write differently but wasn't asked, leave it. Mention it once at the end; do not change it.
- **SHOW DIFFS, NOT FULL REWRITES.** When editing an existing file, produce a unified diff or explicit `str_replace`, not the whole file.
- **PLAN BEFORE IMPLEMENTING** when the task would produce > 100 lines of code. State the plan as 3–7 bullets, wait for "go", then implement.
- **ASK BEFORE DESTRUCTIVE OPS:** file deletion, `git reset --hard`, schema migrations, mass renames, dependency bumps.
- **READ BEFORE WRITING.** If modifying an existing file, read it first (one call). Don't guess current contents.
- **BATCH FILE READS.** If you need three files to understand a change, read them in a single turn, not three.
- **NO FEATURE CREEP.** Do not add logging, caching, retries, rate limiting, or "helpful" abstractions unless I ask.
- **NO STUBBED TODOS.** Do not leave `# TODO: implement this` in code you were asked to implement. Either implement or tell me you can't and why.
- **CITE THE REQUIREMENT.** When you finish a task, state which acceptance criterion from the prompt is now satisfied.

---

## 7. File structure (do not rearrange without asking)

```
codereview-agent/
├── app/
│   ├── main.py              # FastAPI entrypoint, route mounting only
│   ├── config.py            # Settings (pydantic-settings)
│   ├── constants.py         # enums, constants
│   ├── github_auth.py       # GitHub App JWT + installation tokens
│   ├── github_client.py     # Async wrapper around PyGitHub
│   ├── webhook.py           # /webhook route + signature verify
│   ├── models/              # Pydantic models (webhook payloads, LLM I/O)
│   ├── services/            # Business logic (reviewer, pr_fetcher, rag, linters)
│   ├── workers/             # ARQ job functions
│   └── db/
│       ├── models.py        # SQLAlchemy models
│       └── session.py       # Async engine + session factory
├── tests/                   # Mirrors app/ structure
├── eval/                    # Evaluation harness (weekend 5)
├── dashboard/               # Streamlit app (weekend 6)
├── alembic/                 # Migrations
├── secrets/                 # PEM keys — gitignored
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env.example
└── AGENTS.md                # this file
```

New modules go under the right existing folder. **Never create a top-level file in the repo root without asking** (except docs like CHANGELOG.md, CONTRIBUTING.md).

---

## 8. Git & commit conventions

- Commit message format: **Conventional Commits** — `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`.
- Reference the sprint: `feat(webhook): add HMAC signature verification [W1]` for Weekend 1.
- One logical change per commit. No "misc fixes" commits.
- **Never commit directly to `main`.** Use feature branches: `w1/webhook-signature`, `w2/ast-parser`, etc.
- **Never force-push** without asking.

---

## 9. Self-review checklist before reporting a task done

Run through this list. Do not say "done" until all boxes pass:

- [ ] `uv run pytest -v` passes (all tests, not just new ones)
- [ ] `uv run ruff check app/ tests/` clean
- [ ] `uv run mypy app/` clean (or justified `# type: ignore[code]` with reason)
- [ ] No `print()`, no `breakpoint()`, no commented-out code
- [ ] No hardcoded secrets, URLs, or paths outside `config.py`
- [ ] `.env.example` updated if new env vars added
- [ ] New dependencies added to `pyproject.toml` only with prior approval
- [ ] Acceptance criteria from the prompt explicitly restated and ticked off
- [ ] Diff-only output (no repeated unchanged code in response)

---

## 10. LLM-prompt-engineering-specific rules

When working on files under `app/services/reviewer.py` (the module that prompts Gemini):

- **Prompts live in `app/services/prompts/*.md`** as plain markdown, loaded at runtime. Not as Python string constants.
- **Output contract is Pydantic-validated.** If Gemini returns malformed JSON, retry once with a strict-JSON reminder, then give up gracefully.
- **Never trust LLM output blindly** — always validate against the schema before posting to GitHub.
- **Token budget cap: 30k tokens total** (diff + AST + linter output + RAG chunks). Drop lowest-similarity RAG chunks first.

---

## 11. When in doubt

- Ask a clarifying question instead of guessing.
- Propose 2–3 options with trade-offs rather than picking one silently.
- Prefer the boring, standard solution. This is a portfolio project — clever ≠ better.

---

_Last updated: April 18, 2026 — Weekend 1 sprint active._
