"""
Recording, inference, and training utilities for LeRobot
"""

import subprocess
import typer
from pathlib import Path
from rich.prompt import Prompt, Confirm
from typing import Dict
import os
import glob
import re

from solo.commands.robots.lerobot.config import validate_lerobot_config, create_robot_configs, get_known_ids, save_lerobot_config
from solo.commands.robots.lerobot.calibration import display_calibration_error, display_arms_status
from solo.commands.robots.lerobot.auth import authenticate_huggingface
from solo.commands.robots.lerobot.dataset import check_dataset_exists, handle_existing_dataset, normalize_repo_id
from solo.commands.robots.lerobot.cameras import setup_cameras
from solo.commands.robots.lerobot.mode_config import use_preconfigured_args
from solo.commands.robots.lerobot.ports import detect_arm_port, detect_and_retry_ports


def clean_ansi_codes(text: str) -> str:
    """
    Remove ANSI escape codes and clean problematic characters from text to prevent file system errors.
    """
    if not text:
        return text
    
    # Remove ANSI escape codes
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    cleaned = ansi_escape.sub('', text)
    
    # Remove backslashes and other problematic characters for file paths
    cleaned = cleaned.replace('\\', '')
    
    # Remove any remaining control characters
    cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', cleaned)
    
    # Strip whitespace and ensure it's not empty
    cleaned = cleaned.strip()
    
    # If empty after cleaning, provide a safe default
    if not cleaned:
        import time
        cleaned = f"dataset_{int(time.time())}"
    
    return cleaned


def clean_repo_id(repo_id: str) -> str:
    """
    Clean repository ID to be HuggingFace Hub compatible.
    """
    if not repo_id:
        return repo_id
    
    # First clean ANSI codes and basic issues
    cleaned = clean_ansi_codes(repo_id)
    
    # Remove leading slashes
    if cleaned.startswith('/'):
        cleaned = cleaned.lstrip('/')
    
    # Remove trailing slashes
    if cleaned.endswith('/'):
        cleaned = cleaned.rstrip('/')
    
    # Ensure it's not empty
    if not cleaned:
        import time
        cleaned = f"repo_{int(time.time())}"
    
    return cleaned


def generate_unique_repo_id(base_repo_id: str) -> str:
    """
    Generate a unique repo_id by checking for existing directories and incrementing.
    Looks for existing directories matching the pattern and finds the next available number.
    """
    # Check in the HuggingFace cache directory where LeRobot datasets are stored
    cache_dir = os.path.expanduser("~/.cache/huggingface/lerobot/local")
    
    # Look for existing directories matching the pattern
    pattern = f"{base_repo_id}_*"
    existing_dirs = glob.glob(os.path.join(cache_dir, pattern))
    
    # Extract numbers from existing directories
    numbers = []
    for dir_path in existing_dirs:
        dir_name = os.path.basename(dir_path)
        if dir_name.startswith(base_repo_id + "_"):
            try:
                # Extract the number after the underscore
                number_part = dir_name[len(base_repo_id) + 1:]  # Remove base_repo_id + "_"
                if number_part.isdigit():
                    numbers.append(int(number_part))
            except (ValueError, IndexError):
                continue
    
    # Find the next available number
    if not numbers:
        next_number = 1
    else:
        next_number = max(numbers) + 1
    
    return f"{base_repo_id}_{next_number}"


def unified_record_config(
    robot_type: str, 
    leader_port: str, 
    follower_port: str, 
    camera_config: Dict,
    mode: str = "inference",  # "inference" or "recording"
    **mode_specific_kwargs
):
    """
    Create a unified record configuration for both inference and recording modes.
    Uses the same underlying lerobot record infrastructure.
    """
    # Import lerobot components
    from lerobot.scripts.lerobot_record import RecordConfig, DatasetRecordConfig
    from lerobot.configs.policies import PreTrainedConfig
    
    # Create robot configurations
    leader_config, follower_config = create_robot_configs(
        robot_type,
        leader_port,
        follower_port,
        camera_config,
        leader_id=mode_specific_kwargs.get('leader_id'),
        follower_id=mode_specific_kwargs.get('follower_id'),
    )
    
    if follower_config is None:
        raise ValueError(f"Failed to create robot configuration for {robot_type}")
    
    # Configure based on mode
    if mode == "recording":
        # Recording mode - create full dataset configuration
        repo_id = mode_specific_kwargs.get('dataset_repo_id', 'default/dataset')
        
        # Clean ANSI escape codes to prevent file system errors
        repo_id = clean_ansi_codes(repo_id)
        
        # Additional validation: Ensure repo_id doesn't start with '/' or contain problematic characters
        if repo_id.startswith('/'):
            typer.echo(f"⚠️  Warning: repo_id starts with '/', removing it")
            repo_id = repo_id.lstrip('/')
        
        # Ensure repo_id has proper format (owner/name or local/name)
        if '/' not in repo_id:
            repo_id = f"local/{repo_id}"
            typer.echo(f"🔧 Fixed repo_id format: '{repo_id}'")
        
        # Debug: Log the final cleaned repo_id
        typer.echo(f"🔍 Debug - Final repo_id: '{repo_id}'")
        
        push_to_hub = mode_specific_kwargs.get('push_to_hub', False)
        
        # Only force local-only mode if user explicitly wants local-only
        # If push_to_hub is True, convert local/ to username/ format
        if repo_id.startswith('local/') and push_to_hub:
            # Get username from stored credentials
            from solo.commands.robots.lerobot.auth import get_stored_credentials
            stored_username, _ = get_stored_credentials()
            if stored_username:
                # Convert local/name to username/name
                dataset_name = repo_id.split('/', 1)[1]  # Get name after local/
                repo_id = f"{stored_username}/{dataset_name}"
                typer.echo(f"🔧 Converting to HuggingFace format: {repo_id}")
            else:
                typer.echo("⚠️  No HuggingFace username found. Cannot push local dataset to hub.")
                push_to_hub = False
        
        dataset_config = DatasetRecordConfig(
            repo_id=repo_id,
            single_task=mode_specific_kwargs.get('task_description', ''),
            episode_time_s=mode_specific_kwargs.get('episode_time', 60),
            num_episodes=mode_specific_kwargs.get('num_episodes', 50),
            push_to_hub=push_to_hub,
            fps=mode_specific_kwargs.get('fps', 30),
            video=True,
        )
        
        record_config = RecordConfig(
            robot=follower_config,
            teleop=leader_config,
            dataset=dataset_config,
            display_data=True,
            play_sounds=True,
            resume=mode_specific_kwargs.get('should_resume', False),
        )
    
    elif mode == "inference":
        # Inference mode - create minimal configuration with policy
        policy_path = mode_specific_kwargs.get('policy_path')
        if not policy_path:
            raise ValueError("Policy path is required for inference mode")
        
        # Load policy configuration
        policy_config = PreTrainedConfig.from_pretrained(
            policy_path,
            cache_dir=mode_specific_kwargs.get('cache_dir'),
            local_files_only=False,
            force_download=False
        )
        policy_config.pretrained_path = policy_path
        
        # Generate unique repo_id for inference
        policy_path = mode_specific_kwargs.get('policy_path', '')
        policy_name = policy_path.split('/')[-1] if '/' in policy_path else policy_path
        
        # Generate unique repo_id with increment
        base_repo_id = f"eval_{policy_name}"
        repo_id = generate_unique_repo_id(base_repo_id)
        
        # Log the generated repo_id for user awareness
        typer.echo(f"📁 repo_id: {repo_id}")
        
        # Create minimal dataset config for inference (not for recording)
        dataset_config = DatasetRecordConfig(
            repo_id="local/" + repo_id,
            single_task=mode_specific_kwargs.get('task_description', ''),
            episode_time_s=mode_specific_kwargs.get('inference_time', 60),
            num_episodes=1,  # Single inference session
            push_to_hub=False,  # Never push inference sessions
            fps=mode_specific_kwargs.get('fps', 30),
            video=True,
        )
        
        record_config = RecordConfig(
            robot=follower_config,
            teleop=leader_config if mode_specific_kwargs.get('use_teleoperation', False) else None,
            dataset=dataset_config,  # No dataset for pure inference
            policy=policy_config,
            display_data=True,
            play_sounds=False,  # Quieter for inference
            resume=False,
        )
    
    else:
        raise ValueError(f"Unknown mode: {mode}. Must be 'inference' or 'recording'")
    
    return record_config


def recording_mode(config: dict):
    """Handle LeRobot recording mode"""
    typer.echo("🎬 Starting LeRobot recording mode...")
    
    # Check for preconfigured recording settings
    preconfigured = use_preconfigured_args(config, 'recording', 'Recording')
    
    # Initialize variables
    leader_id = None
    follower_id = None
    
    if preconfigured:
        # Use preconfigured settings
        robot_type = preconfigured.get('robot_type')
        leader_port = preconfigured.get('leader_port')
        follower_port = preconfigured.get('follower_port')
        camera_config = preconfigured.get('camera_config')
        leader_id = preconfigured.get('leader_id')
        follower_id = preconfigured.get('follower_id')
        dataset_repo_id = preconfigured.get('dataset_repo_id')
        # Clean ANSI escape codes to prevent file system errors
        if dataset_repo_id:
            dataset_repo_id = clean_ansi_codes(dataset_repo_id)
            
            # Additional validation: Ensure dataset_repo_id doesn't start with '/' or contain problematic characters
            if dataset_repo_id.startswith('/'):
                typer.echo(f"⚠️  Warning: dataset_repo_id starts with '/', removing it")
                dataset_repo_id = dataset_repo_id.lstrip('/')
            
            # Ensure dataset_repo_id has proper format (owner/name or local/name)
            if '/' not in dataset_repo_id:
                dataset_repo_id = f"local/{dataset_repo_id}"
                typer.echo(f"🔧 Fixed dataset_repo_id format: '{dataset_repo_id}'")
        task_description = preconfigured.get('task_description')
        episode_time = preconfigured.get('episode_time')
        num_episodes = preconfigured.get('num_episodes')
        fps = preconfigured.get('fps')
        push_to_hub = preconfigured.get('push_to_hub')
        # When using preconfigured settings, default to resume mode
        should_resume = True
        
        # Validate that we have the required settings
        if not (leader_port and follower_port and robot_type):
            typer.echo("❌ Preconfigured settings missing required robot configuration")
            typer.echo("Please run calibration first or use new settings")
            preconfigured = None
    
    if not preconfigured:
        # Validate configuration using utility function
        leader_port, follower_port, leader_calibrated, follower_calibrated, robot_type = validate_lerobot_config(config)
        
        if not robot_type:
            # Ask for robot type
            typer.echo("\n🤖 Select your robot type:")
            typer.echo("1. SO100")
            typer.echo("2. SO101")
            robot_choice = int(Prompt.ask("Enter robot type", default="2"))
            robot_type = "so100" if robot_choice == 1 else "so101"
            config['robot_type'] = robot_type
        if not leader_port:
            leader_port = detect_arm_port("leader")
            config['leader_port'] = leader_port
        if not follower_port:
            follower_port = detect_arm_port("follower")
            config['follower_port'] = follower_port
        
        # Select ids
        known_leader_ids, known_follower_ids = get_known_ids(config)
        default_leader_id = config.get('lerobot', {}).get('leader_id') or f"{robot_type}_leader"
        default_follower_id = config.get('lerobot', {}).get('follower_id') or f"{robot_type}_follower"
        if known_leader_ids:
            typer.echo("📇 Known leader ids:")
            for i, kid in enumerate(known_leader_ids, 1):
                typer.echo(f"   {i}. {kid}")
        leader_id = Prompt.ask("Enter leader id", default=default_leader_id)
        if known_follower_ids:
            typer.echo("📇 Known follower ids:")
            for i, kid in enumerate(known_follower_ids, 1):
                typer.echo(f"   {i}. {kid}")
        follower_id = Prompt.ask("Enter follower id", default=default_follower_id)

        # Step 1: HuggingFace authentication (optional)
        typer.echo("\n📋 Step 1: HuggingFace Hub Configuration")
        push_to_hub = Confirm.ask("Would you like to push the recorded data to HuggingFace Hub?", default=False)
        hf_username = None
        
        if push_to_hub:
            login_success, hf_username = authenticate_huggingface()
            
            if not login_success:
                typer.echo("❌ HuggingFace authentication failed. Continuing in local-only mode.")
                push_to_hub = False
        else:
            # Even if not pushing to hub, get username for proper repo_id formatting
            from solo.commands.robots.lerobot.auth import get_stored_credentials
            stored_username, _ = get_stored_credentials()
            if stored_username:
                hf_username = stored_username
        
        # Step 2: Get recording parameters
        typer.echo("\n⚙️ Step 2: Recording Configuration")
        
        # Get dataset name and handle existing datasets
        dataset_name = Prompt.ask("Enter dataset repository name", default="lerobot-dataset")
        # Use HuggingFace username if available, otherwise default to "local/" namespace
        initial_repo_id = normalize_repo_id(dataset_name, hf_username=hf_username)
        # Check if dataset exists and handle appropriately
        dataset_repo_id, should_resume = handle_existing_dataset(initial_repo_id)
        # Ensure the returned id still has a namespace (user may have typed name-only)
        dataset_repo_id = normalize_repo_id(dataset_repo_id, hf_username=hf_username)
        # Clean ANSI escape codes to prevent file system errors
        dataset_repo_id = clean_ansi_codes(dataset_repo_id)
        
        # Additional validation: Ensure dataset_repo_id doesn't start with '/' or contain problematic characters
        if dataset_repo_id.startswith('/'):
            typer.echo(f"⚠️  Warning: dataset_repo_id starts with '/', removing it")
            dataset_repo_id = dataset_repo_id.lstrip('/')
        
        # Ensure dataset_repo_id has proper format (owner/name or local/name)
        if '/' not in dataset_repo_id:
            if push_to_hub and hf_username:
                # Use HuggingFace username format for hub uploads
                dataset_repo_id = f"{hf_username}/{dataset_repo_id}"
                typer.echo(f"🔧 Fixed dataset_repo_id format: '{dataset_repo_id}'")
            else:
                # Use local format for local-only datasets
                dataset_repo_id = f"local/{dataset_repo_id}"
                typer.echo(f"🔧 Fixed dataset_repo_id format: '{dataset_repo_id}'")
        
        # Get task description
        task_description = Prompt.ask("Enter task description (e.g., 'Pick up the red cube and place it in the box')")
        
        # Get episode time
        episode_time = float(Prompt.ask("Duration of each recording episode in seconds", default="60"))
        
        # Get number of episodes
        num_episodes = int(Prompt.ask("Total number of episodes to record", default="50"))

        # Setup cameras
        camera_config = setup_cameras()

    # Save configuration before execution (if not using preconfigured settings)
    if not preconfigured:
        from .mode_config import save_recording_config
        recording_args = {
            'robot_type': robot_type,
            'leader_port': leader_port,
            'follower_port': follower_port,
            'camera_config': camera_config,
            'leader_id': leader_id,
            'follower_id': follower_id,
            'dataset_repo_id': dataset_repo_id,
            'task_description': task_description,
            'episode_time': episode_time,
            'num_episodes': num_episodes,
            'fps': 30,
            'push_to_hub': push_to_hub,
            'should_resume': should_resume
        }
        save_recording_config(config, recording_args)

    # Step 3: Start recording
    typer.echo("\n🎬Starting Data Recording")
    typer.echo("Configuration:")
    typer.echo(f"   • Dataset: {dataset_repo_id}")
    typer.echo(f"   • Task: {task_description}")
    typer.echo(f"   • Episode duration: {episode_time}s")
    typer.echo(f"   • Number of episodes: {num_episodes}")
    typer.echo(f"   • Push to hub: {push_to_hub}")
    typer.echo(f"   • Robot type: {robot_type.upper()}")
    try:
        typer.echo(f"   • Leader id: {leader_id}")
        typer.echo(f"   • Follower id: {follower_id}")
    except NameError:
        pass
    
    # Import lerobot recording components
    from lerobot.scripts.lerobot_record import record
    
    try:
        
        # Create unified record configuration for recording mode
        record_config = unified_record_config(
            robot_type=robot_type,
            leader_port=leader_port,
            follower_port=follower_port,
            camera_config=camera_config,
            mode="recording",
            leader_id=leader_id,
            follower_id=follower_id,
            dataset_repo_id=dataset_repo_id,
            task_description=task_description,
            episode_time=episode_time,
            num_episodes=num_episodes,
            push_to_hub=push_to_hub,
            fps=30,
            should_resume=should_resume,
        )
        
        mode_text = "Resuming" if should_resume else "Starting"
        typer.echo(f"🎬 {mode_text} recording... Follow the on-screen instructions.")
        
        if should_resume:
            typer.echo("📝 Note: Recording will continue from existing dataset")
        
        typer.echo("💡 Tips:")
        typer.echo("   • Move the leader arm to control the follower")
        typer.echo("   • Press Right Arrow (→): Early stop the current episode or reset time and move to the next")
        typer.echo("   • Press Left Arrow (←): Cancel the current episode and re-record it")
        typer.echo("   • Press Escape (ESC): Immediately stop the session, encode videos, and upload the dataset")
        
        # Start recording with retry logic
        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                dataset = record(record_config)
                
                mode_text = "resumed and completed" if should_resume else "completed"
                typer.echo(f"✅ Recording {mode_text}!")
                
                # Get the actual dataset name from the record config for display
                actual_repo_id = record_config.dataset.repo_id
                typer.echo(f"📊 Dataset: {actual_repo_id}")
                typer.echo(f"📈 Total episodes in dataset: {dataset.num_episodes}")
                
                if push_to_hub:
                    typer.echo(f"🚀 Dataset pushed to HuggingFace Hub: https://huggingface.co/datasets/{actual_repo_id}")
                
                break  # Success, exit retry loop
                
            except Exception as e:
                error_msg = str(e)
                # Check if it's a port connection error
                if "Could not connect on port" in error_msg or "Make sure you are using the correct port" in error_msg:
                    if attempt < max_retries:
                        typer.echo(f"❌ Connection failed: {error_msg}")
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
                                mode="recording",
                                leader_id=leader_id,
                                follower_id=follower_id,
                                dataset_repo_id=dataset_repo_id,
                                task_description=task_description,
                                episode_time=episode_time,
                                num_episodes=num_episodes,
                                push_to_hub=push_to_hub,
                                fps=30,
                                should_resume=should_resume,
                            )
                            typer.echo("🔄 Retrying recording with new ports...")
                            continue
                        else:
                            typer.echo("❌ Could not find new ports. Please check connections.")
                            return
                    else:
                        typer.echo(f"❌ Recording failed after retry: {error_msg}")
                        return
                elif "Cannot create a file when that file already exists" in error_msg:
                    typer.echo(f"❌ Dataset already exists: {dataset_repo_id}")
                    typer.echo("Please try running the command again.")
                    return
                else:
                    # Non-port related error
                    typer.echo(f"❌ Recording failed: {error_msg}")
                    typer.echo("Please check your robot connections and try again.")
                    return
        
    except KeyboardInterrupt:
        typer.echo("\n🛑 Recording stopped by user.")


def inference_mode(config: dict):
    """Handle LeRobot inference mode"""
    typer.echo("🔮 Starting LeRobot inference mode...")
    
    # Check for preconfigured inference settings
    preconfigured = use_preconfigured_args(config, 'inference', 'Inference')

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
        
        typer.echo("✅ Using preconfigured inference settings")
        
        # Validate that we have the required settings
        if not (follower_port and policy_path):
            typer.echo("❌ Preconfigured settings missing required configuration")
            typer.echo("Please run calibration first or use new settings")
            preconfigured = None
    
    if not preconfigured:
        # Validate configuration using utility function
        leader_port, follower_port, leader_calibrated, follower_calibrated, robot_type = validate_lerobot_config(config)
        
        if not robot_type:
            # Ask for robot type
            typer.echo("\n🤖 Select your robot type:")
            typer.echo("1. SO100")
            typer.echo("2. SO101")
            robot_choice = int(Prompt.ask("Enter robot type", default="2"))
            robot_type = "so100" if robot_choice == 1 else "so101"
            config['robot_type'] = robot_type
        if not follower_port:
            follower_port = detect_arm_port("follower")
            config['follower_port'] = follower_port
        
        typer.echo("✅ Found calibrated follower arm:")
        typer.echo(f"   • Robot type: {robot_type.upper()}")
        typer.echo(f"   • Follower arm: {follower_port}")
        
        # Check if leader arm is available for teleoperation
        use_teleoperation = False
        known_leader_ids, known_follower_ids = get_known_ids(config)
        if leader_port and leader_calibrated:
            use_teleoperation = Confirm.ask("Would you like to teleoperate during inference?", default=False)
            if use_teleoperation:
                default_leader_id = config.get('lerobot', {}).get('leader_id') or f"{robot_type}_leader"
                if known_leader_ids:
                    typer.echo("📇 Known leader ids:")
                    for i, kid in enumerate(known_leader_ids, 1):
                        typer.echo(f"   {i}. {kid}")
                leader_id = Prompt.ask("Enter leader id", default=default_leader_id)
                typer.echo("🎮 Teleoperation enabled - you can override the policy using the leader arm")

        default_follower_id = config.get('lerobot', {}).get('follower_id') or f"{robot_type}_follower"
        if known_follower_ids:
            typer.echo("📇 Known follower ids:")
            for i, kid in enumerate(known_follower_ids, 1):
                typer.echo(f"   {i}. {kid}")
        follower_id = Prompt.ask("Enter follower id", default=default_follower_id)
        
        # Step 1: HuggingFace authentication
        typer.echo("\n📋 Step 1: HuggingFace Authentication")
        login_success, hf_username = authenticate_huggingface()
        
        if not login_success:
            typer.echo("❌ Cannot proceed with inference without HuggingFace authentication.")
            typer.echo("💡 HuggingFace authentication is required to download pre-trained models.")
            return
        
        # Step 2: Get policy path
        typer.echo("\n🤖 Step 2: Policy Configuration")
        policy_path = Prompt.ask("Enter policy path (HuggingFace model ID or local path)")
        
        # Step 3: Inference configuration
        typer.echo("\n⚙️ Step 3: Inference Configuration")
        
        # Get inference duration
        inference_time = float(Prompt.ask("Duration of inference session in seconds", default="60"))
        
        # Get task description (optional for some policies)
        task_description = Prompt.ask("Enter task description", default="")

        # Setup cameras
        camera_config = setup_cameras()
        
        # Save configuration 
        from .mode_config import save_inference_config
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
    import os
    
    try:
        # Set up Windows-specific environment variables for HuggingFace Hub
        os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
        typer.echo(f"📥 Loading model: {policy_path}")

        # Step 4: Start inference
        typer.echo("\n🔮 Step 4: Starting Inference")
        typer.echo("Configuration:")
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
        
        typer.echo("✅ Policy and robot configuration loaded successfully!")
        typer.echo("🔮 Starting inference... Follow the robot's movements.")
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


def training_mode(config: dict):
    """Handle LeRobot training mode"""
    typer.echo("🎓 Starting LeRobot training mode...")
    
    # Check for preconfigured training settings
    preconfigured = use_preconfigured_args(config, 'training', 'Training')
    training_args = {}
    
    if preconfigured:
        # Use preconfigured settings
        dataset_repo_id = preconfigured.get('dataset_repo_id')
        # Clean ANSI escape codes to prevent file system errors
        if dataset_repo_id:
            dataset_repo_id = clean_ansi_codes(dataset_repo_id)
            
            # Additional validation: Ensure dataset_repo_id doesn't start with '/' or contain problematic characters
            if dataset_repo_id.startswith('/'):
                typer.echo(f"⚠️  Warning: dataset_repo_id starts with '/', removing it")
                dataset_repo_id = dataset_repo_id.lstrip('/')
            
            # Ensure dataset_repo_id has proper format (owner/name or local/name)
            if '/' not in dataset_repo_id:
                dataset_repo_id = f"local/{dataset_repo_id}"
                typer.echo(f"🔧 Fixed dataset_repo_id format: '{dataset_repo_id}'")
        
        output_dir = preconfigured.get('output_dir')
        policy_type = preconfigured.get('policy_type')
        training_args = preconfigured.get('training_args', {})
        
        typer.echo("✅ Using preconfigured training settings")
        
        # Validate that we have the required settings
        if not dataset_repo_id:
            typer.echo("❌ Preconfigured settings missing required dataset configuration")
            typer.echo("Please use new settings")
            preconfigured = None
    
    # Get all configuration parameters
    if preconfigured:
        # Use preconfigured settings (dataset_repo_id already cleaned above)
        output_dir = preconfigured.get('output_dir')
        policy_name = preconfigured.get('policy_type')
        training_steps = training_args.get('training_steps', 20000)
        batch_size = training_args.get('batch_size', 8)
        push_to_hub = training_args.get('push_to_hub', True)
        policy_repo_id = training_args.get('policy_repo_id', "")
        use_wandb = training_args.get('use_wandb', True)
        wandb_project = training_args.get('wandb_project', "lerobot-training")
        
        typer.echo(f"✅ Using preconfigured training parameters:")
        typer.echo(f"   • Training steps: {training_steps}")
        typer.echo(f"   • Batch size: {batch_size}")
        typer.echo(f"   • Output directory: {output_dir}")
        typer.echo(f"   • Push to hub: {push_to_hub}")
        typer.echo(f"   • WandB logging: {use_wandb}")
        if policy_repo_id:
            typer.echo(f"   • Policy repository: {policy_repo_id}")
        if use_wandb:
            typer.echo(f"   • WandB project: {wandb_project}")
    else:
        # Get configuration from user input
        dataset_repo_id = Prompt.ask("Enter dataset repository ID", default="lerobot/svla_so101_pickplace")
        
        # Clean ANSI escape codes to prevent file system errors
        dataset_repo_id = clean_ansi_codes(dataset_repo_id)
        
        # Additional validation: Ensure dataset_repo_id doesn't start with '/' or contain problematic characters
        if dataset_repo_id.startswith('/'):
            typer.echo(f"⚠️  Warning: dataset_repo_id starts with '/', removing it")
            dataset_repo_id = dataset_repo_id.lstrip('/')
        
        # Ensure dataset_repo_id has proper format (owner/name or local/name)
        if '/' not in dataset_repo_id:
            # Check if dataset exists on HuggingFace Hub first
            from solo.commands.robots.lerobot.auth import get_stored_credentials
            stored_username, _ = get_stored_credentials()
            
            if stored_username:
                # Try HuggingFace Hub format first
                hf_repo_id = f"{stored_username}/{dataset_repo_id}"
                typer.echo(f"🔍 Checking for dataset on HuggingFace Hub: {hf_repo_id}")
                
                # Check if dataset exists on hub
                if check_dataset_exists(hf_repo_id):
                    dataset_repo_id = hf_repo_id
                    typer.echo(f"✅ Found dataset on HuggingFace Hub: {dataset_repo_id}")
                else:
                    # Fall back to local format
                    dataset_repo_id = f"local/{dataset_repo_id}"
                    typer.echo(f"🔧 Using local dataset: {dataset_repo_id}")
            else:
                # No username available, use local format
                dataset_repo_id = f"local/{dataset_repo_id}"
                typer.echo(f"🔧 Fixed dataset_repo_id format: '{dataset_repo_id}'")
        
        typer.echo("Select policy type:")
        typer.echo("1. SmolVLA (Vision-Language-Action model)")
        typer.echo("2. ACT (Action Chunking with Transformers)")
        typer.echo("3. PI0 (Policy Iteration Zero)")
        typer.echo("4. TDMPC (Temporal Difference MPC)")
        typer.echo("5. Diffusion Policy (good for most tasks)")
        
        policy_choice = Prompt.ask("Enter policy type", default="1")
        policy_name_map = {
            "1": "smolvla",
            "2": "act", 
            "3": "pi0",
            "4": "tdmpc",
            "5": "diffusion"
        }
        policy_name = policy_name_map[policy_choice]
        
        # Step 2: Training configuration
        typer.echo(f"\n⚙️ Step 2: Training Configuration")
        training_steps = int(Prompt.ask("Number of training steps", default="20000"))
        batch_size = int(Prompt.ask("Batch size", default="8"))
        
        # Output directory with conflict resolution
        default_output_dir = f"outputs/train/{dataset_repo_id.replace('/', '_')}_{policy_name}"
        output_dir = Prompt.ask("Output directory for checkpoints", default=default_output_dir)
        
        # Step 3: Hub pushing configuration
        typer.echo(f"\n🚀 Step 3: HuggingFace Hub Configuration")
        push_to_hub = Confirm.ask("Push trained model to HuggingFace Hub?", default=True)
        policy_repo_id = ""
        hf_username = ""
        
        if push_to_hub:
            # HuggingFace authentication for hub pushing
            typer.echo("\n🔐 HuggingFace Authentication for Model Upload")
            login_success, hf_username = authenticate_huggingface()
            
            if not login_success:
                typer.echo("❌ Cannot push to hub without HuggingFace authentication.")
                push_to_hub = False
            else:
                # Get policy repository ID
                policy_name_clean = policy_name.replace("_", "-")
                dataset_name_clean = dataset_repo_id.split("/")[-1].replace("_", "-")
                
                # Clean the dataset name to remove any problematic characters
                dataset_name_clean = clean_ansi_codes(dataset_name_clean)
                if dataset_name_clean.startswith('/'):
                    dataset_name_clean = dataset_name_clean.lstrip('/')
                
                default_policy_repo = f"{hf_username}/{policy_name_clean}-{dataset_name_clean}"
                
                policy_repo_id = Prompt.ask("Enter policy repo id", default=default_policy_repo)
                
                # Clean the policy repository ID to remove any problematic characters
                policy_repo_id = clean_ansi_codes(policy_repo_id)
                if policy_repo_id.startswith('/'):
                    policy_repo_id = policy_repo_id.lstrip('/')
                    typer.echo(f"🔧 Cleaned policy repo ID: {policy_repo_id}")
        
        # Step 4: WandB logging configuration
        typer.echo(f"\n📊 Step 4: Weights & Biases Configuration")
        use_wandb = Confirm.ask("Enable Weights & Biases logging?", default=True)
        wandb_project = ""
        
        if use_wandb:
            # Login to wandb first
            typer.echo("🔐 Logging into Weights & Biases...")
            try:
                result = subprocess.run(["wandb", "login"], check=False)
                if result.returncode != 0:
                    typer.echo("❌ WandB login failed. Continuing without WandB logging.")
                    use_wandb = False
                else:
                    typer.echo("✅ Successfully logged into WandB")
                    wandb_project = Prompt.ask("WandB project name", default="lerobot-training")
            except FileNotFoundError:
                typer.echo("❌ wandb CLI not found. Please install with: pip install wandb")
                typer.echo("Continuing without WandB logging.")
                use_wandb = False
            except Exception as e:
                typer.echo(f"❌ Error during WandB login: {e}")
                typer.echo("Continuing without WandB logging.")
                use_wandb = False
    
    # Debug: Log the final dataset_repo_id before training
    typer.echo(f"🔍 Debug - Final dataset_repo_id for training: '{dataset_repo_id}'")
    
    # Check if dataset exists locally
    if check_dataset_exists(dataset_repo_id):
        typer.echo(f"✅ Found local dataset: {dataset_repo_id}")
    
    # Handle pretrained policy path
    pretrained_policy_path = training_args.get('pretrained_path')
    if pretrained_policy_path:
        typer.echo(f"✅ Using preconfigured pretrained checkpoint: {pretrained_policy_path}")
    elif policy_name == "smolvla":
        pretrained_policy_path = "lerobot/smolvla_base"
        typer.echo(" ℹ️ Using default pretrained SmolVLA checkpoint: lerobot/smolvla_base")
    else:
        pretrained_policy_path = None
    training_args['pretrained_path'] = pretrained_policy_path
    
    # Check if output directory exists and handle conflicts
    output_path = Path(output_dir)
    resume_training = False
    
    if output_path.exists() and output_path.is_dir():
        typer.echo(f"\n⚠️  Output directory already exists: {output_dir}")
        
        # Check if there are checkpoints (indicating a previous training run)
        checkpoint_files = list(output_path.glob("**/*checkpoint*")) + list(output_path.glob("**/*.pt"))
        has_checkpoints = len(checkpoint_files) > 0
        
        if has_checkpoints:
            typer.echo("📁 Found existing checkpoints in directory.")
            choice = Prompt.ask(
                "What would you like to do?",
                choices=["resume", "overwrite", "new_dir"],
                default="resume"
            )
        else:
            typer.echo("📁 Directory exists.")
            choice = Prompt.ask(
                "What would you like to do?", 
                choices=["overwrite", "new_dir"],
                default="overwrite"
            )
        
        if choice == "resume":
            resume_training = True
            typer.echo("🔄 Will resume training from existing checkpoints")
        elif choice == "overwrite":
            import shutil
            shutil.rmtree(output_path)
            typer.echo("🗑️  Removed existing directory")
        elif choice == "new_dir":
            # Generate a unique directory name
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = f"{output_dir}_{timestamp}"
            output_path = Path(output_dir)  # Update output_path too
            typer.echo(f"📁 Using new directory: {output_dir}")
    else:
        typer.echo(f"✅ Directory ready: {output_dir}")
    
    # Step 5: Start training
    typer.echo(f"\n🎓 Step 5: Starting Training")
    typer.echo("Configuration:")
    typer.echo(f"   • Dataset: {dataset_repo_id}")
    typer.echo(f"   • Policy: {policy_name}")
    typer.echo(f"   • Training steps: {training_steps}")
    typer.echo(f"   • Batch size: {batch_size}")
    typer.echo(f"   • Output directory: {output_dir}")
    typer.echo(f"   • Resume training: {resume_training}")
    typer.echo(f"   • Push to Hub: {push_to_hub}")
    if push_to_hub:
        typer.echo(f"   • Policy repository: {policy_repo_id}")
    typer.echo(f"   • WandB logging: {use_wandb}")
    if use_wandb:
        typer.echo(f"   • WandB project: {wandb_project}")
    
    # Save configuration before execution (if not using preconfigured settings)
    if not preconfigured:
        from .mode_config import save_training_config
        training_args = {
            'dataset_repo_id': dataset_repo_id,
            'output_dir': output_dir,
            'policy_type': policy_name,
            'pretrained_policy_path': pretrained_policy_path,
            'training_args': {
                'training_steps': training_steps,
                'batch_size': batch_size,
                'push_to_hub': push_to_hub,
                'policy_repo_id': policy_repo_id,
                'use_wandb': use_wandb,
                'wandb_project': wandb_project
            }
        }
        save_training_config(config, training_args)

    # Import lerobot training components
    from lerobot.scripts.lerobot_train import train
    from lerobot.configs.train import TrainPipelineConfig
    from lerobot.configs.default import DatasetConfig, WandBConfig
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.policies.diffusion.configuration_diffusion import DiffusionConfig
    from lerobot.policies.act.configuration_act import ACTConfig
    from lerobot.policies.tdmpc.configuration_tdmpc import TDMPCConfig
    from lerobot.policies.smolvla.configuration_smolvla import SmolVLAConfig
    from lerobot.policies.pi0.configuration_pi0 import PI0Config
    
    # Suppress warnings
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning, module="torchvision")
    warnings.filterwarnings("ignore", message=".*torch_dtype.*")
    warnings.filterwarnings("ignore", message=".*video decoding.*")
    
    try:
        # Create output directory only if resuming (LeRobot will create it otherwise)
        if resume_training:
            output_path.mkdir(parents=True, exist_ok=True)
        
        # Create dataset config
        dataset_config = DatasetConfig(repo_id=dataset_repo_id)

        # Ensure video decoding backend is available. TorchCodec can be installed without
        # shipping the required FFmpeg shared libraries which causes runtime failures
        # inside the dataloader workers. We proactively fall back to PyAV when
        # TorchCodec cannot be imported.
        if dataset_config.video_backend == "torchcodec":
            try:  # pragma: no cover - best effort guard
                import torchcodec  # noqa: F401
            except Exception as torchcodec_error:
                typer.echo(
                    "⚠️ TorchCodec video backend unavailable ("
                    + str(torchcodec_error)
                    + ") — falling back to PyAV."
                )
                dataset_config.video_backend = "pyav"
        typer.echo(f"   • Video backend: {dataset_config.video_backend}")
        
        # Create policy config based on choice
        if pretrained_policy_path:
            typer.echo(f"📥 Loading pretrained policy config from {pretrained_policy_path}")
            policy_config = PreTrainedConfig.from_pretrained(pretrained_policy_path)
            policy_config.pretrained_path = pretrained_policy_path
            if policy_name and policy_config.type != policy_name:
                typer.echo(
                    f"⚠️ Loaded checkpoint type '{policy_config.type}' does not match selected policy '{policy_name}'."
                )
            policy_name = policy_config.type
        else:
            if policy_name == "diffusion":
                policy_config = DiffusionConfig()
            elif policy_name == "act":
                policy_config = ACTConfig()
            elif policy_name == "tdmpc":
                policy_config = TDMPCConfig()
            elif policy_name == "smolvla":
                policy_config = SmolVLAConfig()
            elif policy_name == "pi0":
                policy_config = PI0Config()
            else:
                raise ValueError(f"Unknown policy type: {policy_name}")
        
        # Set repo_id for hub pushing if configured
        if policy_repo_id:
            # Final cleaning of policy_repo_id before setting
            original_repo_id = policy_repo_id
            policy_repo_id = clean_repo_id(policy_repo_id)
            
            if original_repo_id != policy_repo_id:
                typer.echo(f"🔧 Cleaned policy repo ID: '{original_repo_id}' -> '{policy_repo_id}'")
            
            # Add repo_id as an attribute to the policy config
            policy_config.repo_id = policy_repo_id
            typer.echo(f"🔍 Setting policy repo_id to: '{policy_config.repo_id}'")
        policy_config.push_to_hub = push_to_hub
        
        # Create WandB config
        wandb_config = WandBConfig(
            enable=use_wandb,
            project=wandb_project if use_wandb else None
        )
        
        # Create training config with progress tracking
        train_config = TrainPipelineConfig(
            dataset=dataset_config,
            policy=policy_config,
            output_dir=output_path,
            steps=training_steps,
            batch_size=batch_size,
            save_freq=1000,  # Save checkpoints every 1000 steps
            save_checkpoint=True,
            wandb=wandb_config,
            seed=1000,
            resume=resume_training,  # Use the resume flag we determined above
            rename_map={
                "observation.images.side": "observation.images.camera1",
                "observation.images.up": "observation.images.camera2"
            },
        )
        
        typer.echo("🎓 Starting training... This may take a while.")
        typer.echo("💡 Tips:")
        typer.echo("   • Training progress will be logged to the console")
        typer.echo(f"   • Checkpoints saved every 1000 steps")
        if use_wandb:
            typer.echo(f"   • Monitor progress at https://wandb.ai/{wandb_project}")
        typer.echo("   • Checkpoints will be saved to the output directory")
        typer.echo("   • Press Ctrl+C to stop training early")
        
        # Add progress tracking
        typer.echo(f"\n📊 Training Progress:")
        typer.echo(f"   • Total steps: {training_steps}")
        typer.echo(f"   • Batch size: {batch_size}")
        typer.echo(f"   • Estimated time: {training_steps * batch_size / 1000:.1f} minutes")
        
        # Start training with progress tracking
        typer.echo(f"\n🚀 Starting training at step 0/{training_steps}...")
        typer.echo("📈 Progress will be shown in the console output below...")
        train(train_config)
        
        typer.echo(f"✅ Training completed!")
        typer.echo(f"📊 Dataset: {dataset_repo_id}")
        typer.echo(f"🤖 Policy: {policy_name}")
        typer.echo(f"💾 Checkpoints saved to: {output_dir}")
        
        if push_to_hub and policy_repo_id:
            typer.echo(f"🚀 Model pushed to HuggingFace Hub: https://huggingface.co/{policy_repo_id}")
        
        if use_wandb:
            typer.echo(f"📈 Training logs: https://wandb.ai/{wandb_project}")
        
        
    except KeyboardInterrupt:
        typer.echo("\n🛑 Training stopped by user.")
        typer.echo("💾 Partial checkpoints may have been saved to the output directory.")
    except Exception as e:
        import traceback
        typer.echo(f"❌ Training failed: {e}")
        typer.echo("\n🔍 Full error traceback:")
        typer.echo(traceback.format_exc())
        typer.echo("Please check your dataset and configuration.")
