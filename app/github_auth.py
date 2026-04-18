"""GitHub App JWT signing and installation token exchange.

Handles RS256 JWT generation and installation token caching.
"""

import logging
import time
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import httpx
import jwt

from app.config import get_settings

logger = logging.getLogger(__name__)

# Tokens are valid for 60 minutes; refresh at 50 to avoid edge cases.
_CACHE_TTL = timedelta(minutes=50)


class GitHubAppAuth:
    """Handles GitHub App JWT generation and installation token exchange."""

    def __init__(self, app_id: str, private_key_pem: str) -> None:
        """Initialise with GitHub App credentials.

        Args:
            app_id: The GitHub App ID.
            private_key_pem: The PEM-encoded RSA private key string.
        """
        self.app_id = app_id
        self.private_key_pem = private_key_pem
        self._token_cache: dict[int, tuple[str, datetime]] = {}

    def generate_jwt(self) -> str:
        """Generate an RS256-signed JWT for GitHub App authentication.

        Returns:
            A signed JWT string with iss=app_id, iat=now-60s, exp=now+9min.
        """
        now = int(time.time())
        payload = {
            "iss": self.app_id,
            "iat": now - 60,
            "exp": now + (9 * 60),
        }
        token: str = jwt.encode(payload, self.private_key_pem, algorithm="RS256")
        return token

    async def get_installation_token(self, installation_id: int) -> str:
        """Exchange a JWT for an installation access token.

        Caches tokens by installation_id with a 50-minute TTL.

        Args:
            installation_id: The GitHub App installation ID.

        Returns:
            A valid installation access token string.

        Raises:
            httpx.HTTPStatusError: If the GitHub API returns an error.
        """
        now = datetime.now(UTC)

        # Check cache
        cached = self._token_cache.get(installation_id)
        if cached is not None:
            token, expires_at = cached
            if now < expires_at:
                logger.debug("Cache hit for installation_id=%d", installation_id)
                return token

        # Fetch new token
        token_jwt = self.generate_jwt()
        url = (
            f"https://api.github.com/app/installations/"
            f"{installation_id}/access_tokens"
        )
        headers = {
            "Authorization": f"Bearer {token_jwt}",
            "Accept": "application/vnd.github+json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers)
            response.raise_for_status()
            # response.json() returns Any — we trust GitHub's documented schema
            data: dict[str, Any] = response.json()

        token = str(data["token"])
        expires_at = now + _CACHE_TTL
        self._token_cache[installation_id] = (token, expires_at)
        logger.info("Fetched and cached token for installation_id=%d", installation_id)

        return token


@lru_cache
def get_app_auth() -> GitHubAppAuth:
    """Factory that reads credentials from Settings and returns a GitHubAppAuth.

    The PEM file is loaded once and kept in memory.
    """
    settings = get_settings()
    with open(settings.github_private_key_path) as f:
        private_key_pem = f.read()
    return GitHubAppAuth(
        app_id=str(settings.github_app_id),
        private_key_pem=private_key_pem,
    )
