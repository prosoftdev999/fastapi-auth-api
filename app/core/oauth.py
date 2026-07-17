from typing import Protocol

from authlib.integrations.starlette_client import OAuth

from app.core.config import settings

SUPPORTED_PROVIDERS = {"google", "github", "microsoft"}


class OAuthProviderClient(Protocol):
    """Thin, testable abstraction over an Authlib registered OAuth client.

    Isolating Authlib's API surface behind this protocol means the router
    depends on an interface (not a concrete Authlib class), and tests can
    substitute a fake implementation instead of making real network calls
    to Google/GitHub/Microsoft.
    """

    async def create_authorization_url(self, redirect_uri: str, state: str) -> str: ...

    async def fetch_access_token(self, redirect_uri: str, code: str) -> dict: ...

    async def fetch_identity(self, token: dict) -> tuple[str, str | None]:
        """Returns (provider_user_id, email)."""
        ...


class AuthlibOAuthClient:
    def __init__(self, provider: str, app) -> None:
        self._provider = provider
        self._app = app

    async def create_authorization_url(self, redirect_uri: str, state: str) -> str:
        result = await self._app.create_authorization_url(redirect_uri, state=state)
        return result["url"]

    async def fetch_access_token(self, redirect_uri: str, code: str) -> dict:
        return await self._app.fetch_access_token(
            redirect_uri=redirect_uri, code=code
        )

    async def fetch_identity(self, token: dict) -> tuple[str, str | None]:
        if self._provider == "github":
            return await self._fetch_github_identity(token)

        userinfo = await self._app.userinfo(token=token)
        return str(userinfo["sub"]), userinfo.get("email")

    async def _fetch_github_identity(self, token: dict) -> tuple[str, str | None]:
        profile_response = await self._app.request("GET", "user", token=token)
        profile_response.raise_for_status()
        profile = profile_response.json()

        provider_user_id = str(profile["id"])
        email = profile.get("email")

        if email is None:
            emails_response = await self._app.request(
                "GET", "user/emails", token=token
            )
            emails_response.raise_for_status()
            email = next(
                (
                    item["email"]
                    for item in emails_response.json()
                    if item.get("primary") and item.get("verified")
                ),
                None,
            )

        return provider_user_id, email


_oauth_registry = OAuth()

if settings.google_client_id and settings.google_client_secret:
    _oauth_registry.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url=(
            "https://accounts.google.com/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid email profile"},
    )

if settings.microsoft_client_id and settings.microsoft_client_secret:
    _oauth_registry.register(
        name="microsoft",
        client_id=settings.microsoft_client_id,
        client_secret=settings.microsoft_client_secret,
        server_metadata_url=(
            f"https://login.microsoftonline.com/{settings.microsoft_tenant}"
            "/v2.0/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid email profile"},
    )

if settings.github_client_id and settings.github_client_secret:
    _oauth_registry.register(
        name="github",
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user user:email"},
    )


def get_oauth_client(provider: str) -> OAuthProviderClient | None:
    if provider not in SUPPORTED_PROVIDERS:
        return None

    app = _oauth_registry.create_client(provider)

    if app is None:
        return None

    return AuthlibOAuthClient(provider, app)
