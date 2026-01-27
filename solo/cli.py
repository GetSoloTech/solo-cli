import typer
import sys
from typing import Optional

app = typer.Typer()

# Commands that don't require authentication
NO_AUTH_COMMANDS = {'login', 'setup', 'help'}

@app.callback(invoke_without_command=True)
def check_auth_middleware(ctx: typer.Context):
    """
    Middleware to check authentication before command execution.
    Only triggers for commands that require authentication.
    """
    # If callback was invoked without a command (e.g., just 'solo'), show help
    if ctx.invoked_subcommand is None:
        return
    
    # Get the command name
    command_name = ctx.invoked_subcommand
    
    # Skip auth check for commands that don't require it
    if command_name in NO_AUTH_COMMANDS:
        return
    
    # Check if user is authenticated
    try:
        from solo.auth.auth import is_authenticated
        
        # Check authentication on startup
        if not is_authenticated():
            # Not authenticated, trigger login flow
            from solo.commands.login import login
            login()
            # After login, verify authentication was successful
            # (login() will raise typer.Exit if it fails, so if we get here, it succeeded)
            if not is_authenticated():
                # This shouldn't happen, but handle it gracefully
                sys.exit(1)
    except KeyboardInterrupt:
        # User cancelled login
        sys.exit(0)
    except (SystemExit, typer.Exit):
        # Re-raise system exits (from login or sys.exit)
        raise
    except ImportError:
        # If auth module can't be imported, allow command to proceed (graceful degradation)
        pass
    except Exception:
        # For other errors during auth check, allow command to proceed
        # This prevents auth issues from blocking commands
        pass

# Lazy-loaded commands to improve CLI startup performance

@app.command()
def robo(
    motors: Optional[str] = typer.Option(
        None,
        "--motors",
        help="Setup motor IDs: 'leader', 'follower', or 'all'",
    ),
    calibrate: Optional[str] = typer.Option(
        None,
        "--calibrate",
        help="Calibrate robot arms: 'leader', 'follower', or 'all' (requires motor setup)",
    ),
    teleop: bool = typer.Option(False, "--teleop", help="Start teleoperation (requires calibrated arms)"),
    record: bool = typer.Option(False, "--record", help="Record data for training (requires calibrated arms)"),
    train: bool = typer.Option(False, "--train", help="Train a model (requires recorded data)"),
    inference: bool = typer.Option(False, "--inference", help="Run inference on a pre-trained model"),
    replay: bool = typer.Option(False, "--replay", help="Replay actions from a recorded dataset episode"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Automatically use saved settings if available"),
):
    """
    Robotics operations: motor setup, calibration, teleoperation, data recording, training, and inference
    """
    from solo.commands.robo import robo as _robo
    _robo(motors, calibrate, teleop, record, train, inference, replay, yes)


@app.command()
def setup():
    """
    Set up Solo CLI environment with interactive prompts and saves configuration to config.json.
    """
    from solo.main import setup as _setup
    _setup()


@app.command()
def serve(
    model: Optional[str] = typer.Option(None, "--model", "-m", help="""Model name or path. Can be:
    - HuggingFace repo ID (e.g., 'meta-llama/Llama-3.2-1B-Instruct')
    - Ollama model Registry (e.g., 'llama3.2')
    - Local path to a model file (e.g., '/path/to/model.gguf')
    If not specified, the default model from configuration will be used."""),
    server: Optional[str] = typer.Option(None, "--server", "-s", help="Server type (ollama, vllm, llama.cpp)"), 
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Port to run the server on"),
    ui: Optional[bool] = typer.Option(True, "--ui", help="Start the UI for the server")
):
    """Start a model server with the specified model.
    
    If no server is specified, uses the server type from configuration.
    To set up your configuration, run 'solo setup' first.
    """
    from solo.commands.serve import serve as _serve
    _serve(model, server, port, ui)


@app.command()
def status():
    """Check running models, system status, and configuration."""
    from solo.commands.status import status as _status
    _status()


@app.command(name="list")
def list_models():
    """
    List all downloaded models available in HuggingFace cache and Ollama.
    """
    from solo.commands.models_list import list as _list
    _list()


@app.command()
def test(
    timeout: Optional[int] = typer.Option(None, "--timeout", "-t", help="Request timeout in seconds. Default is 30s for vLLM/Llama.cpp and 120s for Ollama.")
):
    """
    Test if the Solo CLI is running correctly.
    Performs an inference test to verify server functionality.
    """
    from solo.commands.test import test as _test
    _test(timeout)


@app.command()
def stop(name: str = typer.Option("", help="Server type to stop (e.g., 'ollama', 'vllm', 'llama.cpp')")):
    """
    Stops Solo CLI services. If a server type is specified (e.g., 'ollama', 'vllm', 'llama.cpp'),
    only that specific service will be stopped. Otherwise, all Solo services will be stopped.
    """
    from solo.commands.stop import stop as _stop
    _stop(name)


@app.command()
def download(model: str):
    """
    Downloads a Hugging Face model using the huggingface repo id.
    """
    from solo.commands.download_hf import download as _download
    _download(model)


@app.command()
def login():
    """
    Login to Solo CLI using device code flow.
    Displays a user code and verification URL, then polls for authorization.
    """
    from solo.commands.login import login as _login
    _login()


if __name__ == "__main__":
    app()
