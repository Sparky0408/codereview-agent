# Contributing to CodeReview Agent

Thank you for your interest in contributing! This guide covers the development workflow, testing requirements, and conventions.

## Development Setup

**Prerequisites:** Python 3.12, [uv](https://docs.astral.sh/uv/), Docker & Docker Compose.

```bash
git clone https://github.com/Sparky0408/codereview-agent.git
cd codereview-agent
uv sync
docker compose up postgres redis -d
cp .env.example .env   # edit with your values
uv run pytest -v
```

## Running Tests

```bash
uv run pytest -v                       # full suite
uv run pytest --cov=app --cov=dashboard # with coverage
```

- **No live API calls.** Mock GitHub with `respx`, mock Gemini with stubs.
- **Every new public function** needs at least one test (happy path + failure).
- **Coverage target:** 80%+ on new code.

## Linting & Type Checking

```bash
uv run ruff check app/ tests/ dashboard/
uv run mypy app/
```

## Branch Naming

```
w1/webhook-signature    # sprint work
fix/webhook-timeout     # non-sprint fixes
docs/architecture       # documentation
```

## Commit Messages — [Conventional Commits](https://www.conventionalcommits.org/)

```
feat(webhook): add HMAC signature verification [W1]
fix(reviewer): handle empty diff gracefully
test(feedback): add acceptance rate edge cases
```

## Pull Request Process

1. Create a feature branch from `main`.
2. Run before opening: `uv run pytest -v`, `uv run ruff check`, `uv run mypy app/`.
3. Open a PR with a clear description. One logical change per PR.
4. Never force-push without discussing first.

## Code Style

- Type hints on every function. Async for all I/O. Files < 300 lines.
- No `print()` in `app/` — use `logging.getLogger(__name__)`.
- Docstrings on all public functions (Google style).
- Constants in `app/constants.py`.

## Adding Dependencies

Ask before adding any new dependency. Test-only deps (e.g., `freezegun`) are fine to add without asking.

## Code of Conduct

[Contributor Covenant v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
