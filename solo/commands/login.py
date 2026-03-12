from rich.console import Console

console = Console()


def login(force: bool = False) -> None:
    """Device-code login flow for Solo Hub."""
    from solo.hub.auth import device_code_login
    from solo.hub.errors import SoloAuthError

    try:
        device_code_login(force=force)
    except SoloAuthError as e:
        console.print(f"Login failed: {e}", style="bold red")
    except Exception as e:
        console.print(f"Unexpected error during login: {e}", style="bold red")
