"""
Inference mode for LeRobot
Handles running pretrained policies on the robot
"""

import os
from pathlib import Path
import typer
from rich.prompt import Prompt, Confirm

from solo.commands.robots.lerobot.config import (
    validate_lerobot_config,
)
from solo.commands.robots.lerobot.auth import authenticate_huggingface
from solo.commands.robots.lerobot.cameras import setup_cameras
from solo.commands.robots.lerobot.mode_config import use_preconfigured_args
from solo.commands.robots.lerobot.ports import detect_and_retry_ports
from solo.commands.robots.lerobot.utils.record_config import unified_record_config


def _find_latest_local_model() -> str | None:
    """
    Auto-detect the latest trained model from common output directories.
    
    Looks for models in:
    - outputs/train/*/checkpoints/last/pretrained_model
    - outputs/train/*/checkpoints/*/pretrained_model (sorted by step number)
    
    Returns the path to the latest model's pretrained_model directory, or None if not found.
    """
    output_dirs = [
        Path("outputs/train"),
        Path.home() / "outputs/train",
        Path.cwd() / "outputs/train",
    ]
    
    latest_model = None
    latest_time = None
    
    for output_dir in output_dirs:
        if not output_dir.exists():
            continue
            
        # Find all training run directories
        for run_dir in output_dir.rglob("checkpoints"):
            if not run_dir.is_dir():
                continue
            
            # First, check for "last" symlink (preferred)
            last_checkpoint = run_dir / "last" / "pretrained_model"
            if last_checkpoint.exists():
                # Check if it has the required files
                if (last_checkpoint / "config.json").exists() or (last_checkpoint / "model.safetensors").exists():
                    try:
                        mtime = last_checkpoint.stat().st_mtime
                        if latest_time is None or mtime > latest_time:
                            latest_time = mtime
                            latest_model = str(last_checkpoint)
                    except OSError:
                        pass
                continue
            
            # If no "last" symlink, find the highest numbered checkpoint
            checkpoint_dirs = []
            for item in run_dir.iterdir():
                if item.is_dir() and item.name.isdigit():
                    pretrained_dir = item / "pretrained_model"
                    if pretrained_dir.exists():
                        if (pretrained_dir / "config.json").exists() or (pretrained_dir / "model.safetensors").exists():
                            checkpoint_dirs.append((int(item.name), pretrained_dir))
            
            if checkpoint_dirs:
                # Sort by step number (highest first)
                checkpoint_dirs.sort(key=lambda x: x[0], reverse=True)
                best_checkpoint = checkpoint_dirs[0][1]
                try:
                    mtime = best_checkpoint.stat().st_mtime
                    if latest_time is None or mtime > latest_time:
                        latest_time = mtime
                        latest_model = str(best_checkpoint)
                except OSError:
                    pass
    
    return latest_model


def inference_mode(config: dict, auto_use: bool = False):
    """Handle LeRobot inference mode"""
    # Check for preconfigured inference settings
    preconfigured, detected_robot_type = use_preconfigured_args(config, 'inference', 'Inference', auto_use=auto_use)

    # Initialize variables
    leader_id = None
    follower_id = None
    
    if preconfigured:
        # Use preconfigured settings
        robot_type = preconfigured.get('robot_type')
        leader_port = preconfigured.get('leader_port')
        leader_id = preconfigured.get('leader_id')
        follower_port = preconfigured.get('follower_port')
        follower_id = preconfigured.get('follower_id')
        camera_config = preconfigured.get('camera_config')
        policy_path = preconfigured.get('policy_path')
        task_description = preconfigured.get('task_description')
        inference_time = preconfigured.get('inference_time')
        fps = preconfigured.get('fps')
        use_teleoperation = preconfigured.get('use_teleoperation')
        
        # Get calibration status from config for preconfigured settings
        leader_calibrated = config.get('lerobot', {}).get('leader_calibrated', False)
        follower_calibrated = config.get('lerobot', {}).get('follower_calibrated', False)
        
        # Check if policy_path is a local path
        if policy_path:
            is_local_policy = Path(policy_path).exists() or policy_path.startswith("/") or policy_path.startswith("./") or policy_path.startswith("~")
            if is_local_policy:
                expanded_path = Path(policy_path).expanduser()
                if not expanded_path.exists():
                    typer.echo(f"⚠️  Local model path not found: {policy_path}")
                    preconfigured = None
                else:
                    typer.echo(f"📂 Using local model: {policy_path}")
        
        # Validate that we have the required settings
        if not (follower_port and policy_path):
            typer.echo("❌ Preconfigured settings missing required configuration")
            typer.echo("Please run calibration first or use new settings")
            preconfigured = None
    
    if not preconfigured:
        # Validate configuration using utility function
        leader_port, follower_port, leader_calibrated, follower_calibrated, saved_robot_type = validate_lerobot_config(config)
        
        # Use detected robot type if available (e.g., from mismatch detection), otherwise use saved
        robot_type = detected_robot_type if detected_robot_type else saved_robot_type
        
        if not robot_type:
            from solo.commands.robots.lerobot.utils.helper import auto_detect_robot
            robot_type = auto_detect_robot(default="so101")
            config['robot_type'] = robot_type
        
        # Handle port/connection based on robot type
        from solo.commands.robots.lerobot.config import is_realman_robot
        from solo.commands.robots.lerobot.utils.helper import get_realman_configs, port_detection, prompt_arm_id
        if is_realman_robot(robot_type):
            # RealMan: Load network config
            realman_config = get_realman_configs(config)
            config['realman_config'] = realman_config
            follower_port = None  # Network-based, no USB port
            
            typer.echo("✅ Found RealMan follower (network):")
            typer.echo(f"   • Robot type: {robot_type.upper()}")
            typer.echo(f"   • Follower: {realman_config.get('ip')}:{realman_config.get('port')}")
        else:
            follower_port = port_detection(config, "follower", robot_type, follower_port)
            
            typer.echo("✅ Found calibrated follower arm:")
            typer.echo(f"   • Robot type: {robot_type.upper()}")
            typer.echo(f"   • Follower arm: {follower_port}")
        
        # Check if leader arm is available for teleoperation
        use_teleoperation = False
        if leader_port and leader_calibrated:
            use_teleoperation = Confirm.ask("Would you like to teleoperate during inference?", default=False)
            if use_teleoperation:
                leader_id = prompt_arm_id(config, "leader", robot_type)
                typer.echo("🎮 Teleoperation enabled - you can override the policy using the leader arm")

        follower_id = prompt_arm_id(config, "follower", robot_type)
        
        # Step 1: Get policy path first to determine if auth is needed
        typer.echo("\n🤖 Step 1: Policy Configuration")

        # Choose model source
        model_source = Prompt.ask(
            "Where is your model?",
            choices=["solo", "huggingface", "local"],
            default="solo",
        )

        if model_source == "solo":
            # Solo Hub model
            from solo.hub.auth import ensure_authenticated
            from solo.hub.errors import SoloAuthError
            try:
                ensure_authenticated()
            except SoloAuthError:
                typer.echo("❌ Not logged in to Solo Hub. Run 'solo login' first.")
                return

            typer.echo("💡 Enter your Solo Hub model ID (e.g., org/model_name)")
            solo_model_id = Prompt.ask("Solo Hub model ID")
            policy_path = f"solo:{solo_model_id}"
            typer.echo(f"\n📡 Using Solo Hub model: {solo_model_id}")

        elif model_source == "local":
            typer.echo("💡 Enter a local path (e.g., /path/to/model or ./outputs/train/checkpoint)")

            # Auto-detect latest local trained model
            default_policy_path = _find_latest_local_model()
            if default_policy_path:
                typer.echo(f"📂 Found latest local model: {default_policy_path}")

            policy_path = Prompt.ask("Enter local model path", default=default_policy_path or "")
            expanded_path = Path(policy_path).expanduser()
            if not expanded_path.exists():
                typer.echo(f"❌ Local model path not found: {policy_path}")
                typer.echo("💡 Please check the path and try again.")
                return
            typer.echo(f"\n📂 Using local model: {policy_path}")

        else:
            # HuggingFace model
            typer.echo("💡 Enter a HuggingFace model ID (e.g., lerobot/act_so100_test)")

            # Auto-detect latest local trained model as fallback default
            default_policy_path = _find_latest_local_model()

            policy_path = Prompt.ask("HuggingFace model ID", default=default_policy_path or "")

            # Check if user accidentally entered a local path
            expanded_path = Path(policy_path).expanduser()
            if expanded_path.exists():
                typer.echo(f"\n📂 Detected local model: {policy_path}")
            else:
                # HuggingFace authentication required
                typer.echo("\n📋 Step 2: HuggingFace Authentication")
                typer.echo("💡 HuggingFace authentication is required to download pre-trained models.")
                login_success, hf_username = authenticate_huggingface()

                if not login_success:
                    typer.echo("❌ Cannot proceed with inference without HuggingFace authentication.")
                    typer.echo("💡 If using a local model, provide the full path (e.g., /path/to/model or ./model)")
                    return
        
        # Step 3: Inference configuration
        typer.echo("\n⚙️ Step 3: Inference Configuration")
        fps = 30  # Default FPS
        
        # Get inference duration
        inference_time = float(Prompt.ask("Duration of inference session in seconds", default="60"))
        
        # Get task description (optional for some policies)
        task_description = Prompt.ask("Enter task description", default="")

        # Setup cameras
        camera_config = setup_cameras()
        
        # Save configuration 
        from solo.commands.robots.lerobot.mode_config import save_inference_config
        inference_args = {
            'robot_type': robot_type,
            'leader_port': leader_port,
            'leader_id': leader_id,
            'follower_id': follower_id,
            'follower_port': follower_port,
            'camera_config': camera_config,
            'policy_path': policy_path,
            'task_description': task_description,
            'inference_time': inference_time,
            'fps': 30,
            'use_teleoperation': use_teleoperation
        }
        save_inference_config(config, inference_args)
    
    # Import lerobot inference components
    from lerobot.scripts.lerobot_record import record
    
    try:
        # Set up Windows-specific environment variables for HuggingFace Hub
        os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'

        typer.echo("\n🔮 Starting Inference")
        typer.echo(f"   • Policy: {policy_path}")
        typer.echo(f"   • Inference duration: {inference_time}s")
        typer.echo(f"   • Task: {task_description or 'Not specified'}")
        typer.echo(f"   • Robot type: {robot_type.upper()}")
        typer.echo(f"   • Teleoperation: {'Enabled' if use_teleoperation else 'Disabled'}")
        
        # Create unified record configuration for inference mode
        record_config = unified_record_config(
            robot_type=robot_type,
            leader_port=leader_port,
            leader_id=leader_id,
            follower_id=follower_id,
            follower_port=follower_port,
            camera_config=camera_config,
            mode="inference",
            policy_path=policy_path,
            task_description=task_description,
            inference_time=inference_time,
            fps=30,
            use_teleoperation=use_teleoperation,
        )
        
        typer.echo("💡 Tips:")
        if use_teleoperation:
            typer.echo("   • The robot will execute the policy autonomously")
            typer.echo("   • Move the leader arm to override the policy")
            typer.echo("   • Release the leader arm to let the policy take control")
        else:
            typer.echo("   • The robot will execute the policy autonomously")
        typer.echo("   • Press Right Arrow (→): Early stop the current episode or reset time and move to the next")
        typer.echo("   • Press Left Arrow (←): Cancel the current episode and re-record it")
        typer.echo("   • Press Escape (ESC): Immediately stop the session, encode videos, and upload the dataset")
        
        # Start inference with retry logic
        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                # Start inference using unified record function (without dataset)
                record(record_config)
                
                typer.echo("\n✅ Inference completed successfully!")
                
                break  # Success, exit retry loop
                
            except Exception as e:
                error_msg = str(e)
                # Check if it's a port connection error
                if "Could not connect on port" in error_msg or "Make sure you are using the correct port" in error_msg:
                    if attempt < max_retries:
                        typer.echo(f"❌ Connection failed: {error_msg}")
                        
                        # For RealMan, skip port retry (network-based, not USB)
                        from solo.commands.robots.lerobot.config import is_realman_robot
                        if is_realman_robot(robot_type):
                            typer.echo("❌ RealMan connection failed. Please check network settings in realman_config.yaml")
                            return
                        
                        typer.echo("🔄 Attempting to detect new ports...")
                        
                        # Detect new ports and retry
                        new_leader_port, new_follower_port = detect_and_retry_ports(leader_port, follower_port, config)
                        
                        if new_leader_port != leader_port or new_follower_port != follower_port:
                            # Update ports and recreate config
                            leader_port, follower_port = new_leader_port, new_follower_port
                            record_config = unified_record_config(
                                robot_type=robot_type,
                                leader_port=leader_port,
                                follower_port=follower_port,
                                camera_config=camera_config,
                                mode="inference",
                                policy_path=policy_path,
                                task_description=task_description,
                                inference_time=inference_time,
                                fps=30,
                                use_teleoperation=use_teleoperation,
                            )
                            typer.echo("🔄 Retrying inference with new ports...")
                            continue
                        else:
                            typer.echo("❌ Could not find new ports. Please check connections.")
                            return
                    else:
                        typer.echo(f"❌ Inference failed after retry: {error_msg}")
                        return
                else:
                    # Non-port related error
                    typer.echo(f"❌ Inference failed: {error_msg}")
                    typer.echo("💡 Troubleshooting tips:")
                    typer.echo("   • Check if the model path is correct")
                    typer.echo("   • Ensure you have internet connection for HuggingFace models")
                    typer.echo("   • Verify HuggingFace authentication is working")
                    typer.echo("   • For local paths, ensure the file exists and is accessible")
                    return
        
    except PermissionError as e:
        typer.echo(f"❌ Permission error loading policy: {e}")
        
    except KeyboardInterrupt:
        typer.echo("\n🛑 Inference stopped by user.")

