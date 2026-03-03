import typer
from typing import Optional

app = typer.Typer()

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
    scan: bool = typer.Option(False, "--scan", help="Scan for connected motors on all serial ports"),
    diagnose: bool = typer.Option(False, "--diagnose", help="Run detailed connection diagnostics on all ports"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Automatically use saved settings if available"),
    # Replay-specific options (non-interactive)
    dataset: Optional[str] = typer.Option(None, "--dataset", help="Dataset repository ID for replay (e.g., 'organize_fennel_seed')"),
    episode: Optional[int] = typer.Option(None, "--episode", help="Episode number to replay (default: 0)"),
    follower_id: Optional[str] = typer.Option(None, "--follower-id", help="Follower arm ID for replay (e.g., 'follower_right')"),
    fps: Optional[int] = typer.Option(None, "--fps", help="Frames per second for replay (default: 30)"),
):
    """
    Robotics operations: motor setup, calibration, teleoperation, data recording, training, replay, and inference
    """
    if scan:
        from solo.commands.robots.lerobot.scan import scan_motors
        scan_motors()
        return
    if diagnose:
        from solo.commands.robots.lerobot.scan import diagnose_all_ports
        diagnose_all_ports()
        return
    from solo.commands.robo import robo as _robo
    _robo(motors, calibrate, teleop, record, train, inference, replay, yes, dataset, episode, follower_id, fps)


@app.command()
def setup():
    """
    Set up Solo CLI environment with interactive prompts and saves configuration to config.json.
    """
    from solo.main import setup as _setup
    _setup()


@app.command()
def login():
    """
    Authenticate with Solo by getting a token from hub.getsolo.tech
    """
    from solo.commands.login import login as _login
    _login()


@app.command()
def logout():
    """
    Log out from Solo by removing the authentication token
    """
    from solo.commands.login import logout as _logout
    _logout()


@app.command()
def whoami():
    """
    Display current authentication status and user information
    """
    from solo.commands.login import whoami as _whoami
    _whoami()


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


@app.command(name="setup-usb")
def setup_usb_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt (Linux only)")
):
    """
    Set up USB permissions for LeRobot-compatible robot arms.
    
    On Linux: Installs udev rules and adds user to dialout group.
    On macOS: Checks for connected devices and provides driver info.
    
    Supports Koch (Dynamixel), SO100/SO101 (Feetech/Waveshare) arms.
    Run once after installing solo-cli.
    """
    from solo.commands.setup_usb import setup_usb
    setup_usb(auto_confirm=yes)


if __name__ == "__main__":
    app()
