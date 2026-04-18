"""Fetches PR file diffs via PyGitHub.

PyGitHub is synchronous — all calls are wrapped with asyncio.to_thread.
"""

import asyncio
import logging

from github import Auth, Github

logger = logging.getLogger(__name__)


async def fetch_pr_diff(
    repo_full_name: str,
    pr_number: int,
    installation_token: str,
) -> list[tuple[str, str]]:
    """Fetch changed files and their patches for a pull request.

    Args:
        repo_full_name: Owner/repo string (e.g. "octocat/Hello-World").
        pr_number: Pull request number.
        installation_token: GitHub App installation access token.

    Returns:
        List of (filename, patch) tuples. Patch is empty string for binary files.
    """

    def _fetch_sync() -> list[tuple[str, str]]:
        g = Github(auth=Auth.Token(installation_token))
        repo = g.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        return [(f.filename, f.patch or "") for f in pr.get_files()]

    return await asyncio.to_thread(_fetch_sync)
