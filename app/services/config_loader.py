"""Loads and parses .codereview.yml from repositories."""

import asyncio
import logging
from typing import Any

import yaml
from github import Auth, Github
from github.GithubException import GithubException, UnknownObjectException
from pydantic import ValidationError

from app.models.repo_config import RepoConfig

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Service to load and validate repository configuration."""

    async def load_config(
        self, repo_full_name: str, installation_token: str, head_sha: str
    ) -> RepoConfig:
        """Fetches .codereview.yml from repo root via PyGitHub and parses it.

        Args:
            repo_full_name: Repository owner/name.
            installation_token: Access token for GitHub API.
            head_sha: Commit SHA of the PR head to fetch configuration from.

        Returns:
            RepoConfig: Parsed configuration or defaults if not found/invalid.
        """

        def _fetch_yaml() -> str | None:
            g = Github(auth=Auth.Token(installation_token))
            try:
                repo = g.get_repo(repo_full_name)
                content_file = repo.get_contents(".codereview.yml", ref=head_sha)
                if isinstance(content_file, list):
                    return None
                return content_file.decoded_content.decode("utf-8")
            except UnknownObjectException:
                logger.debug(".codereview.yml not found at %s", head_sha)
                return None
            except GithubException as e:
                if e.status == 404:
                    logger.debug(".codereview.yml returning 404 at %s", head_sha)
                    return None
                logger.warning("Failed to fetch .codereview.yml: %s", e)
                return None
            except Exception as e:
                logger.warning("Unexpected error fetching config: %s", e)
                return None

        content = await asyncio.to_thread(_fetch_yaml)
        if not content:
            return RepoConfig()

        try:
            parsed: dict[str, Any] | None = yaml.safe_load(content)
            if not isinstance(parsed, dict):
                logger.warning("Malformed YAML in .codereview.yml, returning defaults.")
                return RepoConfig()

            return RepoConfig.model_validate(parsed)
        except yaml.YAMLError as e:
            logger.warning("Failed to parse YAML in .codereview.yml: %s", e)
            return RepoConfig()
        except ValidationError as e:
            logger.warning("Invalid configuration in .codereview.yml: %s", e)
            return RepoConfig()
