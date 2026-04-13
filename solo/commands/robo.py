"""
Robotics command for Solo CLI
Framework: LeRobot
"""

import json
import os
import typer
from solo.config import CONFIG_PATH
from solo.commands.robots.lerobot import lerobot


def robo(
    motors: str,
    calibrate: str,
    teleop: bool,
    record: bool,
    train: bool,
    inference: bool,
    replay: bool,
    yes: bool,
    # Replay-specific options (non-interactive)
    dataset: str = None,
    episode: int = None,
    follower_id: str = None,
    fps: int = None,
    dry_run: bool = False,
):
    """
    Robotics operations: motor setup, calibration, teleoperation, data recording, training, replay, and inference
    """
    # Load existing config
    config = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
            
            # Migrate legacy known_ids format to structured format (by robot type)
            from solo.commands.robots.lerobot.config import migrate_known_ids_to_structured
            migrate_known_ids_to_structured(config)
        except (json.JSONDecodeError, FileNotFoundError):
            config = {}
    
    # Pass replay options to handler
    replay_options = {
        'dataset': dataset,
        'episode': episode,
        'follower_id': follower_id,
        'fps': fps
    } if replay else None
    
    # Use LeRobot handler directly
    lerobot.handle_lerobot(config, calibrate, motors, teleop, record, train, inference, replay, yes, replay_options, dry_run) 