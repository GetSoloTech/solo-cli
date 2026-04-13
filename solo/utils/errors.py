import sys
import json
import typer

class ErrorCodes:
    SUCCESS = 0
    GENERAL_ERROR = 100
    HARDWARE_ERROR = 101
    CONFIG_ERROR = 102
    MODELS_ERROR = 103
    AUTH_ERROR = 104
    NETWORK_ERROR = 105

def exit_with_error(message: str, code: int = ErrorCodes.GENERAL_ERROR, details: dict = None, output_format: str = "text"):
    \"\"\"
    Standardizes how the CLI exits when encountering an error, making it machine parseable.
    \"\"\"
    if output_format.lower() == "json":
        error_payload = {
            "error": True,
            "message": message,
            "code": code
        }
        if details is not None:
            error_payload["details"] = details
        print(json.dumps(error_payload, indent=2), file=sys.stderr)
    else:
        typer.secho(f"Error ({code}): {message}", fg=typer.colors.RED, err=True)
        if details:
            typer.secho(f"Details: {details}", fg=typer.colors.YELLOW, err=True)
    
    raise typer.Exit(code=code)
