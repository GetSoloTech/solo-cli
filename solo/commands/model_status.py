from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

STATUS_STYLES = {
    "completed": "bold green",
    "failed": "bold red",
    "cancelled": "bold red",
    "training": "bold yellow",
    "queued": "bold blue",
    "provisioning": "bold blue",
    "initializing": "bold blue",
    "uploading model": "bold yellow",
}


def model_status(model: str) -> None:
    """Check the training status of a model on Solo Hub."""
    from solo.hub import parse_solo_ref
    from solo.hub.client import SoloHubClient
    from solo.hub.errors import SoloAuthError, SoloHubError

    clean_id = parse_solo_ref(model)

    parts = clean_id.split("/", 1)
    if len(parts) != 2:
        console.print(
            f"Invalid model identifier '{clean_id}'. Expected format: [bold]org/model_name[/bold]",
            style="bold red",
        )
        return

    _, model_name = parts

    try:
        client = SoloHubClient()
        model_info = client.get_model_info(model_name)
    except SoloAuthError as e:
        console.print(f"{e}", style="bold red")
        return
    except SoloHubError as e:
        console.print(f"{e}", style="bold red")
        return

    status = (model_info.get("status") or "unknown").lower()
    status_display = status.replace("_", " ").title()
    style = STATUS_STYLES.get(status, "bold")

    name = model_info.get("name", model_name)
    model_type = model_info.get("modelType", "N/A")
    framework = model_info.get("framework", "N/A")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("Model", name)
    table.add_row("Status", f"[{style}]{status_display}[/{style}]")
    if model_type != "N/A":
        table.add_row("Type", model_type)
    if framework != "N/A":
        table.add_row("Framework", framework)

    console.print(Panel(table, title=f"Model Status: [cyan]{clean_id}[/cyan]", border_style="blue"))

    if status == "completed":
        console.print(
            f"\nModel is ready! Run [bold]solo download {clean_id}[/bold] to download.",
            style="dim",
        )
    elif status in ("failed", "cancelled"):
        console.print(
            f"\nTraining {status_display.lower()}. This model cannot be downloaded.",
            style="dim",
        )
    else:
        console.print(
            f"\nTraining is still in progress. Check back later with [bold]solo status {clean_id}[/bold].",
            style="dim",
        )
