import os

from rich.console import Console

from solo.hub.constants import SOLO_TOKEN_PATH, SOLO_USER_PATH

console = Console()


def logout() -> None:
    """Log out of Solo Hub by removing stored credentials."""
    removed = False

    for path in (SOLO_TOKEN_PATH, SOLO_USER_PATH):
        if os.path.exists(path):
            os.remove(path)
            removed = True

    if removed:
        console.print("Successfully logged out.", style="bold green")
    else:
        console.print("Not currently logged in.", style="dim")
