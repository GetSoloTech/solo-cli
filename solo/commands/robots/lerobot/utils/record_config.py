"""
Record configuration utilities for LeRobot
Provides unified configuration for recording and inference modes
"""

import typer
from typing import Dict

from solo.commands.robots.lerobot.config import (
    get_robot_config_classes,
    create_robot_configs,
    is_bimanual_robot,
    is_realman_robot,
    create_bimanual_leader_config,
    create_bimanual_follower_config,
)
from .text_cleaning import clean_ansi_codes, generate_unique_repo_id


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
    Supports single-arm, bimanual, and RealMan robots.
    
    For RealMan robots:
    - leader_port: USB port for SO101 leader arm
    - follower_port: Not used (RealMan uses network)
    - realman_config: Network configuration for RealMan (passed in mode_specific_kwargs)
    """
    # Import lerobot components
    from lerobot.scripts.lerobot_record import RecordConfig, DatasetRecordConfig
    from lerobot.configs.policies import PreTrainedConfig
    
    # Check if RealMan robot (network-based follower)
    if is_realman_robot(robot_type):
        # RealMan: SO101 leader (USB) + RealMan follower (network)
        from lerobot.teleoperators.so101_leader import SO101LeaderConfig
        from solo.commands.robots.lerobot.realman_config import create_realman_follower_config
        
        # Create SO101 leader config
        leader_config = SO101LeaderConfig(
            port=leader_port,
            id=mode_specific_kwargs.get('leader_id', 'so101_leader')
        )
        
        # Create RealMan follower config
        realman_config = mode_specific_kwargs.get('realman_config', {})
        if not realman_config:
            # Try to load from file
            from solo.commands.robots.lerobot.realman_config import load_realman_config
            realman_config = load_realman_config()
        
        follower_config = create_realman_follower_config(
            realman_config,
            camera_config,
            follower_id=mode_specific_kwargs.get('follower_id', 'realman_r1d2_follower')
        )
    
    # Check if bimanual robot
    elif is_bimanual_robot(robot_type):
        # Bimanual configuration
        leader_config_class, follower_config_class = get_robot_config_classes(robot_type)
        
        if leader_config_class is None or follower_config_class is None:
            raise ValueError(f"Unsupported bimanual robot type: {robot_type}")
        
        # Get bimanual ports from kwargs
        left_leader_port = mode_specific_kwargs.get('left_leader_port')
        right_leader_port = mode_specific_kwargs.get('right_leader_port')
        left_follower_port = mode_specific_kwargs.get('left_follower_port')
        right_follower_port = mode_specific_kwargs.get('right_follower_port')
        
        if not all([left_leader_port, right_leader_port, left_follower_port, right_follower_port]):
            raise ValueError("Bimanual robots require all 4 ports: left_leader, right_leader, left_follower, right_follower")
        
        leader_config = create_bimanual_leader_config(
            leader_config_class,
            left_leader_port,
            right_leader_port,
            robot_type,
            leader_id=mode_specific_kwargs.get('leader_id')
        )
        
        follower_config = create_bimanual_follower_config(
            follower_config_class,
            left_follower_port,
            right_follower_port,
            robot_type,
            camera_config,
            follower_id=mode_specific_kwargs.get('follower_id')
        )
    else:
        # Single-arm configuration
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
            num_episodes=mode_specific_kwargs.get('num_episodes', 10),
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

        # Resolve Solo Hub references to a local snapshot directory so that
        # all downstream loaders (config, weights, processor pipelines) can
        # read files directly without needing solo: awareness.
        from solo.hub import is_solo_ref, parse_solo_ref
        if is_solo_ref(policy_path):
            from solo.hub import solo_snapshot_download
            clean_id = parse_solo_ref(policy_path)
            typer.echo(f"Downloading model from Solo Hub: {clean_id}...")
            local_model_path = solo_snapshot_download(repo_id=clean_id)
            typer.echo(f"Model cached at: {local_model_path}")
        else:
            local_model_path = policy_path

        # Load policy configuration from the resolved local path
        policy_config = PreTrainedConfig.from_pretrained(
            local_model_path,
            cache_dir=mode_specific_kwargs.get('cache_dir'),
            local_files_only=False,
            force_download=False
        )
        policy_config.pretrained_path = local_model_path

        # Generate unique repo_id for inference
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

