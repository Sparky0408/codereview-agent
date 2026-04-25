<![CDATA[# Configuration Reference

CodeReview Agent is configured per-repository via a `.codereview.yml` file in the repository root. When the file is absent, sensible defaults are used.

## Full Schema

```yaml
# .codereview.yml — place in your repository root

# Master switch. Set to false to disable the bot on this repo.
enabled: true                       # default: true

# Languages to review. Files in other languages are skipped.
languages:                          # default: [python, javascript, typescript]
  - python
  - javascript
  - typescript

# Glob patterns for paths to ignore (never reviewed).
ignore_paths:                       # default: []
  - "docs/**"
  - "tests/fixtures/**"
  - "*.generated.py"
  - "vendor/**"

# Review rules — tune the bot's sensitivity.
review_rules:
  max_function_lines: 50            # default: 50 — flag functions longer than this
  max_cyclomatic_complexity: 10     # default: 10 — flag functions above this complexity
  max_function_args: 5              # default: 5  — flag functions with more arguments
  severity_threshold: NITPICK       # default: NITPICK — minimum severity to post
                                    #   CRITICAL → only post critical issues
                                    #   SUGGESTION → post suggestions and above
                                    #   NITPICK → post everything
  max_comments_per_file: 10         # default: 10 — cap comments per file
  max_total_comments: 25            # default: 25 — cap total comments per PR
  banned_patterns:                  # default: [] — flag these patterns in code
    - "TODO"
    - "HACK"
    - "FIXME"
```

## Field Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `bool` | `true` | Master switch for the bot on this repo |
| `languages` | `list[str]` | `[python, javascript, typescript]` | Languages to review |
| `ignore_paths` | `list[str]` | `[]` | Glob patterns for paths to skip |
| `review_rules.max_function_lines` | `int` | `50` | Maximum lines per function before flagging |
| `review_rules.max_cyclomatic_complexity` | `int` | `10` | Maximum cyclomatic complexity |
| `review_rules.max_function_args` | `int` | `5` | Maximum function arguments |
| `review_rules.severity_threshold` | `str` | `NITPICK` | Minimum severity to post (`CRITICAL`, `SUGGESTION`, `NITPICK`) |
| `review_rules.max_comments_per_file` | `int` | `10` | Maximum comments per file |
| `review_rules.max_total_comments` | `int` | `25` | Maximum total comments per PR |
| `review_rules.banned_patterns` | `list[str]` | `[]` | String patterns to flag when found in code |

## Example Configurations

### Strict Mode (CI-like)

Focus only on critical issues. Good for large repos where noise is a concern.

```yaml
enabled: true
languages: [python]
ignore_paths:
  - "tests/**"
  - "docs/**"
  - "scripts/**"
review_rules:
  max_function_lines: 40
  max_cyclomatic_complexity: 8
  max_function_args: 4
  severity_threshold: CRITICAL
  max_comments_per_file: 5
  max_total_comments: 10
```

### Lenient Mode (Learning)

Post everything including nitpicks. Good for teams wanting comprehensive feedback.

```yaml
enabled: true
languages: [python, javascript, typescript]
ignore_paths: []
review_rules:
  max_function_lines: 80
  max_cyclomatic_complexity: 15
  max_function_args: 8
  severity_threshold: NITPICK
  max_comments_per_file: 15
  max_total_comments: 40
  banned_patterns:
    - "TODO"
    - "HACK"
    - "FIXME"
    - "XXX"
```

### Python-Only

```yaml
enabled: true
languages: [python]
ignore_paths:
  - "frontend/**"
  - "*.js"
  - "*.ts"
```

### Security-Focused

Focus on security findings — combine with a lower complexity threshold.

```yaml
enabled: true
languages: [python, javascript]
ignore_paths:
  - "docs/**"
review_rules:
  max_function_lines: 60
  max_cyclomatic_complexity: 8
  max_function_args: 5
  severity_threshold: CRITICAL
  max_comments_per_file: 5
  max_total_comments: 15
  banned_patterns:
    - "eval("
    - "exec("
    - "subprocess.call"
    - "os.system"
    - "pickle.loads"
    - "yaml.load"
```

## Environment Variables

These are set in `.env` (or passed via Docker Compose) and apply globally:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_APP_ID` | Yes | — | GitHub App ID |
| `GITHUB_PRIVATE_KEY_PATH` | No | `secrets/codereview-agent.pem` | Path to the App's PEM private key |
| `GITHUB_WEBHOOK_SECRET` | Yes | — | Webhook secret for HMAC verification |
| `DATABASE_URL` | No | `postgresql+asyncpg://codereview:codereview@localhost:5432/codereview` | PostgreSQL connection string |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis URL for the task queue |
| `GEMINI_API_KEY` | Yes | — | Google Gemini API key |
| `DEBUG` | No | `false` | Enable debug logging and SQLAlchemy echo |
]]>
