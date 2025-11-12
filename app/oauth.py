import os
import json
import requests
import streamlit as st
from dotenv import load_dotenv
from importlib import metadata as importlib_metadata

load_dotenv()


def _get_env(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name, default)
    return val


def has_google_oauth_config() -> bool:
    return bool(_get_env("GOOGLE_CLIENT_ID") and _get_env("GOOGLE_CLIENT_SECRET"))


def can_render_google_button() -> bool:
    if not has_google_oauth_config():
        return False
    try:
        from streamlit_oauth import OAuth2Component  # noqa: F401
        return True
    except Exception:
        return False


def oauth_diagnostics() -> dict:
    """Return diagnostics about Google OAuth configuration and component availability."""
    info: dict[str, object] = {}
    client_id = _get_env("GOOGLE_CLIENT_ID")
    client_secret = _get_env("GOOGLE_CLIENT_SECRET")
    info["has_client_id"] = bool(client_id)
    info["has_client_secret"] = bool(client_secret)
    info["redirect_uri"] = _get_env("OAUTH_REDIRECT_URI", "http://localhost:8501")
    try:
        from streamlit_oauth import OAuth2Component  # noqa: F401
        info["component_import"] = True
        try:
            version = importlib_metadata.version("streamlit-oauth")
        except Exception:
            version = None
        info["component_version"] = version
    except Exception as e:
        info["component_import"] = False
        info["component_error"] = str(e)
    return info


def google_login_button(label: str = "Continue with Google") -> dict | None:
    """Render a Google OAuth login button and return user info on success.

    Requires environment variables:
      - GOOGLE_CLIENT_ID
      - GOOGLE_CLIENT_SECRET

    This implementation uses streamlit-oauth for the OAuth dance, then calls
    Google's userinfo endpoint to retrieve the user's email/name/picture.
    """
    try:
        from streamlit_oauth import OAuth2Component
    except Exception:
        st.warning("OAuth component not available. Install streamlit-oauth and restart.")
        return None

    client_id = _get_env("GOOGLE_CLIENT_ID")
    client_secret = _get_env("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        st.warning("Google OAuth is not configured (missing client id/secret).")
        return None

    # OAuth endpoints for Google
    authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    revoke_url = "https://oauth2.googleapis.com/revoke"
    refresh_url = token_url
    # Redirect to current page
    # Redirect URI must match what you configure in Google Console
    # For local development this is typically http://localhost:8501
    redirect_uri = _get_env("OAUTH_REDIRECT_URI", "http://localhost:8501")

    oauth2 = OAuth2Component(
        client_id=client_id,
        client_secret=client_secret,
        authorize_endpoint=authorize_url,
        token_endpoint=token_url,
        refresh_token_endpoint=refresh_url,
        revoke_token_endpoint=revoke_url,
    )

    # Call with PKCE set to S256 (as required by streamlit-oauth); fall back if signature differs
    try:
        result = oauth2.authorize_button(
            name=label,
            icon="https://developers.google.com/identity/images/g-logo.png",
            redirect_uri=redirect_uri,
            scope="openid email profile",
            pkce="S256",
        )
    except TypeError:
        # Older versions may not support the pkce argument
        result = oauth2.authorize_button(
            name=label,
            icon="https://developers.google.com/identity/images/g-logo.png",
            redirect_uri=redirect_uri,
            scope="openid email profile",
        )

    if not result or "token" not in result:
        return None

    token = result["token"]
    access_token = token.get("access_token")
    if not access_token:
        return None

    # Fetch user info
    try:
        resp = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        info = resp.json()
        # Normalize fields
        return {
            "email": info.get("email"),
            "name": info.get("name"),
            "picture": info.get("picture"),
            "sub": info.get("sub"),
            "provider": "google",
        }
    except Exception:
        return None
