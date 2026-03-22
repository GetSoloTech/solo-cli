import json
from rich.console import Console

console = Console()

def print_output(data: dict, output_format: str = "text", text_renderer=None):
    \"\"\"
    Prints output either as raw JSON (for AI agents/machines) or using a human-readable text_renderer.
    :param data: The structured dictionary representing the state/result.
    :param output_format: 'text' or 'json'.
    :param text_renderer: A callable that accepts the data dict and renders it using rich/typer.
    \"\"\"
    if output_format.lower() == "json":
        print(json.dumps(data, indent=2))
    else:
        if text_renderer:
            text_renderer(data)
        else:
            # Fallback to simple print if no text renderer is provided
            print(data)
