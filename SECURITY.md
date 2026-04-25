# Security Policy

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please report them via one of these channels:

1. **GitHub Security Advisories** — [Report a vulnerability](https://github.com/Sparky0408/codereview-agent/security/advisories/new) (preferred)
2. **Email** — Contact the maintainer directly via GitHub profile

We will acknowledge your report within 48 hours and aim to release a fix within 7 days for critical issues.

## Scope

The following are in scope for security reports:

| Area | Examples |
|------|----------|
| **Webhook signature bypass** | HMAC-SHA256 verification flaws, timing attacks |
| **Secret exposure** | Tokens, API keys, or PEM keys leaked in logs, responses, or error messages |
| **Prompt injection** | Crafted PR content that causes the LLM to execute unintended actions |
| **SQL injection** | Malformed input reaching the database layer |
| **Dependency vulnerabilities** | Known CVEs in direct dependencies |

## Out of Scope

- LLM hallucinations or inaccurate review comments (these are quality issues, not security)
- Rate limiting (not yet implemented — tracked as a feature)
- Denial of service via large PRs (mitigated by token budgets, but not a security boundary)

## Security Design

- **All credentials** are loaded from environment variables via `app/config.py` — never hardcoded.
- **Webhook signature verification** is mandatory on every incoming request.
- **GitHub App authentication** uses short-lived installation tokens (JWT → token exchange).
- **No secrets are logged** — the logging configuration explicitly excludes sensitive fields.
- **`.env` and `secrets/`** are in `.gitignore`.

## Supported Versions

| Version | Supported |
|---------|-----------|
| `main` branch | ✅ |
| Older commits | ❌ |

This is an actively developed project. Security fixes are applied to `main` only.
