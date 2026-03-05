import json
import os
import time

import requests
from rich.console import Console

from solo.hub.constants import (
    DEVICE_CODE_ENDPOINT,
    DEVICE_TOKEN_ENDPOINT,
    SOLO_CONFIG_DIR,
    SOLO_HUB_API_BASE,
    SOLO_TOKEN_PATH,
    SOLO_USER_PATH,
    USER_PROFILE_ENDPOINT,
)
from solo.hub.errors import SoloAuthError

console = Console()


def get_stored_token() -> str | None:
    """Read token from ~/.solo/token. Returns None if missing or empty."""
    if not os.path.exists(SOLO_TOKEN_PATH):
        return None
    try:
        with open(SOLO_TOKEN_PATH) as f:
            token = f.read().strip()
    except OSError:
        return None
    return token or None


def save_token(token: str) -> None:
    """Write token to ~/.solo/token with restricted permissions."""
    os.makedirs(SOLO_CONFIG_DIR, exist_ok=True)
    with open(SOLO_TOKEN_PATH, "w") as f:
        f.write(token)
    os.chmod(SOLO_TOKEN_PATH, 0o600)


def get_user_profile(token: str) -> dict:
    """Fetch user profile from Solo Hub API."""
    url = f"{SOLO_HUB_API_BASE}{USER_PROFILE_ENDPOINT}"
    try:
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
    except requests.ConnectionError:
        raise SoloAuthError("Could not connect to Solo Hub. Check your internet connection.")
    except requests.Timeout:
        raise SoloAuthError("Request to Solo Hub timed out. Please try again later.")
    if resp.status_code == 401:
        raise SoloAuthError("Token is invalid or expired. Run 'solo login' to re-authenticate.")
    if resp.status_code != 200:
        raise SoloAuthError(f"Failed to fetch profile (HTTP {resp.status_code}). Please try again later.")
    return resp.json()


def save_user_profile(profile: dict) -> None:
    """Extract and save basic user info to ~/.solo/user.json."""
    os.makedirs(SOLO_CONFIG_DIR, exist_ok=True)

    memberships = profile.get("memberships", [])
    org = memberships[0].get("organization", {}) if memberships else {}

    data = {
        "name": profile.get("name", ""),
        "email": profile.get("email", ""),
        "org_id": org.get("id", ""),
    }
    with open(SOLO_USER_PATH, "w") as f:
        json.dump(data, f, indent=2)


def device_code_login(force: bool = False) -> str:
    """
    Full device-code OAuth flow.

    1. POST /device-code -> get device_code, user_code, verification_url
    2. Display instructions to user
    3. Poll /device-token until authorized or timeout
    4. Save token and user profile

    Returns the access token.
    """
    if not force:
        existing = get_stored_token()
        if existing:
            try:
                profile = get_user_profile(existing)
                username = profile.get("userName", profile.get("name", "Unknown"))
                console.print(f"Already logged in as [bold cyan]{username}[/bold cyan].")
                console.print("Run [bold]solo login --force[/bold] to re-authenticate.")
                return existing
            except Exception:
                pass  # Token expired, proceed with login

    # Step 1: Initiate device code flow
    url = f"{SOLO_HUB_API_BASE}{DEVICE_CODE_ENDPOINT}"
    try:
        resp = requests.post(url, timeout=15)
    except requests.ConnectionError:
        raise SoloAuthError("Could not connect to Solo Hub. Check your internet connection.")
    except requests.Timeout:
        raise SoloAuthError("Request to Solo Hub timed out. Please try again later.")
    if resp.status_code != 200:
        raise SoloAuthError(f"Failed to start login (HTTP {resp.status_code}). Please try again later.")
    data = resp.json()

    device_code = data.get("deviceCode") or data.get("device_code")
    user_code = data.get("userCode") or data.get("user_code")
    verification_url = data.get("verification_url") or data.get("verificationUrl", SOLO_HUB_API_BASE)
    interval = data.get("interval", data.get("intervals", 5))
    expires_in_ms = data.get("expires_in", 300000)
    expires_in = expires_in_ms / 1000 if expires_in_ms > 1000 else expires_in_ms

    if not device_code or not user_code:
        raise SoloAuthError("Failed to initiate device code flow. Unexpected API response.")

    # Step 2: Display instructions and offer to open browser
    console.print()
    console.print(f"[bold]To authenticate, visit:[/bold] {verification_url}")
    console.print(f"[bold]Enter code:[/bold] [bold green]{user_code}[/bold green]")
    console.print()

    try:
        response = console.input("[dim]Press Enter to open the browser (or type 'skip' to open manually):[/dim] ")
        if response.strip().lower() != "skip":
            import webbrowser
            webbrowser.open(verification_url)
            console.print("Browser opened.", style="dim")
    except (EOFError, KeyboardInterrupt):
        pass

    console.print()
    console.print("Waiting for authorization...", style="dim")

    # Step 3: Poll for token
    token_url = f"{SOLO_HUB_API_BASE}{DEVICE_TOKEN_ENDPOINT}"
    deadline = time.time() + expires_in

    while time.time() < deadline:
        time.sleep(interval)
        try:
            token_resp = requests.post(
                token_url,
                json={"deviceCode": device_code},
                timeout=15,
            )
            if token_resp.status_code == 200:
                token_data = token_resp.json()
                token = token_data.get("token") or token_data.get("access_token")
                if token:
                    # Step 4: Save token and profile
                    save_token(token)
                    try:
                        profile = get_user_profile(token)
                        save_user_profile(profile)
                        username = profile.get("userName", profile.get("name", "Unknown"))
                        console.print(f"\nSuccessfully logged in as [bold cyan]{username}[/bold cyan].")
                    except Exception:
                        console.print("\nToken saved. Could not fetch profile.")
                    return token

            # 400/404 means "authorization_pending" - keep polling
            if token_resp.status_code in (400, 404):
                continue

            # Other errors
            if token_resp.status_code == 401:
                raise SoloAuthError("Device code was denied.")

        except requests.RequestException:
            continue  # Network hiccup, keep polling

    raise SoloAuthError("Login timed out. Run 'solo login' to try again.")


def ensure_authenticated() -> str:
    """Return a valid token or raise SoloAuthError."""
    token = get_stored_token()
    if not token:
        raise SoloAuthError("Not logged in. Run 'solo login' first.")
    return token
