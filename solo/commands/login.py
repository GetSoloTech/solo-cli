import typer
import os
import json
import webbrowser
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from solo.config import CONFIG_PATH

console = Console()


def is_authenticated():
    """
    Check if the user is authenticated

    Returns:
        tuple: (bool, str) - (is_authenticated, token or None)
    """
    if not os.path.exists(CONFIG_PATH):
        return False, None

    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)

        if 'auth' in config and 'solo_token' in config['auth']:
            return True, config['auth']['solo_token']
    except json.JSONDecodeError:
        pass

    return False, None


def require_auth():
    """
    Decorator/helper function to require authentication for a command

    Returns:
        str: token if authenticated, None otherwise (prints error message)
    """
    authenticated, token = is_authenticated()

    if not authenticated:
        typer.echo("❌ You are not authenticated. Please run 'solo login' first.")
        return None

    return token


def login():
    """
    Authenticate with Solo by getting a token from hub.getsolo.tech
    """
    console.print(Panel.fit(
        "[bold cyan]Solo Login[/bold cyan]\n\n"
        "To use Solo CLI, you need to authenticate with a token.\n"
        "Visit [bold yellow]hub.getsolo.tech[/bold yellow] to get your token.",
        title="Authentication Required"
    ))

    # Open hub.getsolo.tech in browser
    try:
        typer.echo("\n🌐 Opening hub.getsolo.tech in your browser...")
        webbrowser.open("https://hub.getsolo.tech")
    except Exception as e:
        typer.echo(f"⚠️  Could not open browser automatically: {e}")
        typer.echo("Please manually visit: https://hub.getsolo.tech")

    # Prompt user to input their token
    typer.echo("\n")
    token = typer.prompt("Enter your Solo token", hide_input=True)

    if not token or not token.strip():
        typer.echo("❌ No token provided. Login cancelled.")
        return

    # Load existing config or create new one
    config = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
        except json.JSONDecodeError:
            config = {}

    # Save token to config
    if 'auth' not in config:
        config['auth'] = {}

    config['auth']['solo_token'] = token.strip()

    # Create config directory if it doesn't exist
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

    # Save configuration to file
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)

    typer.secho("\n✅ Successfully logged in to Solo!", fg=typer.colors.GREEN)
    typer.echo(f"Token saved to {CONFIG_PATH}")


def logout():
    """
    Log out from Solo by removing the authentication token
    """
    # Check if config exists
    if not os.path.exists(CONFIG_PATH):
        typer.echo("❌ No configuration found. You are not logged in.")
        return

    # Load config
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError:
        typer.echo("❌ Error reading configuration file.")
        return

    # Check if auth token exists
    if 'auth' not in config or 'solo_token' not in config['auth']:
        typer.echo("❌ You are not logged in.")
        return

    # Remove token
    del config['auth']['solo_token']

    # Remove auth section if empty
    if not config['auth']:
        del config['auth']

    # Save updated config
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)

    typer.secho("✅ Successfully logged out from Solo!", fg=typer.colors.GREEN)


def whoami():
    """
    Display current authentication status and user information
    """
    from rich.table import Table

    # Check if config exists
    if not os.path.exists(CONFIG_PATH):
        typer.echo("❌ No configuration found. Please run 'solo setup' first.")
        return

    # Load config
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError:
        typer.echo("❌ Error reading configuration file.")
        return

    # Check authentication status
    is_authenticated = 'auth' in config and 'solo_token' in config['auth']

    # Create status table
    table = Table(title="Solo Authentication Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    if is_authenticated:
        token = config['auth']['solo_token']
        # Mask token for security (show first 8 and last 4 characters)
        if len(token) > 12:
            masked_token = f"{token[:8]}...{token[-4:]}"
        else:
            masked_token = "***"

        table.add_row("Status", "✅ Authenticated")
        table.add_row("Token", masked_token)
    else:
        table.add_row("Status", "❌ Not authenticated")
        table.add_row("Token", "N/A")

    # Add other user info if available
    if 'user' in config:
        user_config = config['user']
        if 'domain' in user_config:
            table.add_row("Domain", user_config['domain'])

    console.print(table)

    if not is_authenticated:
        typer.echo("\nTo authenticate, run: solo login")
