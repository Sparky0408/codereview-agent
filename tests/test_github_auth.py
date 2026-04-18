"""Tests for GitHub App authentication."""

import time
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.github_auth import GitHubAppAuth

INSTALL_URL = "https://api.github.com/app/installations/42/access_tokens"


@pytest.fixture
def rsa_keypair() -> tuple[str, str]:
    """Generate an ephemeral RSA keypair for testing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


@pytest.fixture
def auth(rsa_keypair: tuple[str, str]) -> GitHubAppAuth:
    """Create a GitHubAppAuth instance with the test keypair."""
    private_pem, _ = rsa_keypair
    return GitHubAppAuth(app_id="12345", private_key_pem=private_pem)


class TestGenerateJwt:
    """Tests for GitHubAppAuth.generate_jwt."""

    def test_jwt_decodable_with_correct_claims(
        self,
        auth: GitHubAppAuth,
        rsa_keypair: tuple[str, str],
    ) -> None:
        """JWT should decode with the public key and have correct iss + exp."""
        _, public_pem = rsa_keypair
        token = auth.generate_jwt()

        decoded = jwt.decode(token, public_pem, algorithms=["RS256"])

        assert decoded["iss"] == "12345"

        now = time.time()
        # exp should be within a 10-minute window from now
        assert decoded["exp"] > now
        assert decoded["exp"] <= now + 10 * 60


class TestGetInstallationToken:
    """Tests for GitHubAppAuth.get_installation_token."""

    @pytest.mark.asyncio
    async def test_first_call_hits_endpoint(self, auth: GitHubAppAuth) -> None:
        """First call should POST to GitHub and return the token."""
        with respx.mock:
            route = respx.post(INSTALL_URL).mock(
                return_value=httpx.Response(201, json={"token": "ghs_test123"})
            )
            token = await auth.get_installation_token(42)

        assert token == "ghs_test123"
        assert route.call_count == 1

    @pytest.mark.asyncio
    async def test_second_call_returns_cached(self, auth: GitHubAppAuth) -> None:
        """Second call with same installation_id should use cache (call_count==1)."""
        with respx.mock:
            route = respx.post(INSTALL_URL).mock(
                return_value=httpx.Response(201, json={"token": "ghs_test123"})
            )
            token1 = await auth.get_installation_token(42)
            token2 = await auth.get_installation_token(42)

        assert token1 == token2 == "ghs_test123"
        assert route.call_count == 1

    @pytest.mark.asyncio
    async def test_expired_cache_refetches(self, auth: GitHubAppAuth) -> None:
        """After cache expires (51min), a new request should be made."""
        with respx.mock:
            route = respx.post(INSTALL_URL).mock(
                return_value=httpx.Response(201, json={"token": "ghs_refreshed"})
            )
            await auth.get_installation_token(42)

            # Backdate the cached expires_at so it appears expired
            auth._token_cache[42] = (
                "ghs_stale",
                datetime.now(UTC) - timedelta(minutes=1),
            )

            token = await auth.get_installation_token(42)

        assert token == "ghs_refreshed"
        assert route.call_count == 2
