from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def whoami() -> None:
    """Display current user profile, organization, and subscription info."""
    from solo.hub.auth import ensure_authenticated
    from solo.hub.client import SoloHubClient
    from solo.hub.errors import SoloAuthError

    from solo.state import state

    is_json = state.get("output_format", "text") == "json"

    try:
        token = ensure_authenticated()
    except SoloAuthError as e:
        if is_json:
            import json
            print(json.dumps({"error": str(e)}, indent=2))
        else:
            console.print(f"{e}", style="bold red")
        return

    try:
        client = SoloHubClient(token=token)
        profile = client.whoami()
    except SoloAuthError as e:
        if is_json:
            import json
            print(json.dumps({"error": str(e)}, indent=2))
        else:
            console.print(f"{e}", style="bold red")
        return
    except Exception as e:
        if is_json:
            import json
            print(json.dumps({"error": f"Failed to fetch profile: {e}"}, indent=2))
        else:
            console.print(f"Failed to fetch profile: {e}", style="bold red")
        return

    if is_json:
        import json
        print(json.dumps(profile, indent=2))
        return

    # User info
    name = profile.get("name", "N/A")
    email = profile.get("email", "N/A")
    username = profile.get("userName", "N/A")

    # Subscription info from organization
    memberships = profile.get("memberships", [])
    if memberships:
        org = memberships[0].get("organization", {})
        org_sub = org.get("orgSubscription", {})
        subscription = org_sub.get("subscription", {})
        sub_title = subscription.get("title", "Free")
    else:
        sub_title = "Free"

    # Build display
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("Name", name)
    table.add_row("Email", email)
    table.add_row("Username", username)
    table.add_row("Subscription", sub_title)

    console.print(Panel(table, title="Solo Hub Profile", border_style="blue"))
