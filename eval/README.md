# Evaluation Harness

Replays historical merged PRs through the CodeReview Agent pipeline (in dry-run mode) and measures how well the bot's comments align with actual human reviewer comments.

## Prerequisites

- Python 3.12+
- `uv` package manager with project dependencies installed
- `GEMINI_API_KEY` — your Gemini API key (set in `.env`)
- `GITHUB_EVAL_PAT` — a GitHub Personal Access Token with `public_repo` scope for reading public repositories

## Setup

```bash
# Add tokens to your .env file
echo 'GITHUB_EVAL_PAT=ghp_your_pat_here' >> .env

# Or export directly
export GITHUB_EVAL_PAT=ghp_your_pat_here
export GEMINI_API_KEY=your_key_here
```

## Usage

```bash
# Evaluate against 5 recent merged PRs from starlette
python -m eval.run --repo encode/starlette --prs 5 --output eval_report.md

# Full evaluation (20 PRs, default)
python -m eval.run --repo encode/starlette --output eval_report.md

# Write to stdout
python -m eval.run --repo encode/starlette --prs 3

# Use a specific Gemini model
python -m eval.run --repo encode/starlette --prs 5 --gemini-model gemini-2.5-pro --output eval_report.md
```

## CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--repo` | *(required)* | Target repo in `owner/name` format |
| `--prs` | `20` | Number of merged PRs to evaluate |
| `--output` | stdout | Output file for the markdown report |
| `--gemini-model` | `gemini-2.5-flash` | Gemini model (Flash saves cost) |

## How It Works

1. **Fetch** — Queries GitHub GraphQL API for recently merged PRs that have line-level review comments
2. **Replay** — Runs each PR through the full review pipeline (AST analysis → Gemini review) in dry-run mode (no comments posted to GitHub)
3. **Match** — Compares bot-generated comments against human comments using fuzzy matching:
   - Same file
   - Within ±3 lines
   - ≥2 significant shared words
4. **Report** — Outputs precision, recall, and F1 score with per-PR and per-severity breakdowns

## Interpreting Results

- **Precision** = TP / (TP + FP) — "Of what the bot flagged, how much was also flagged by humans?"
- **Recall** = TP / (TP + FN) — "Of what humans flagged, how much did the bot catch?"
- **F1** = Harmonic mean of precision and recall

> **Note:** Low precision is expected since the bot may catch valid issues that humans didn't comment on. Low recall is also expected since human comments include style/context that a bot can't replicate. Focus on the F1 trend over time as you tune prompts.

## Cost Estimate

Using `gemini-2.5-flash` (default):
- ~5k tokens per PR (diff + AST context + prompt)
- 20 PRs ≈ 100k tokens ≈ $0.02

Using `gemini-2.5-pro`:
- Same input, 10x cost ≈ $0.20 for 20 PRs
