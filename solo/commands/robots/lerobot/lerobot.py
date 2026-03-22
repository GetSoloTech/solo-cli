"""
LeRobot framework handler for Solo CLI
Handles LeRobot motor setup, calibration, teleoperation, data recording, and training
"""

import typer
from rich.console import Console


console = Console()

def handle_lerobot(config: dict, calibrate: str, motors: str, teleop: bool, record: bool, train: bool, inference: bool = False, replay: bool = False, auto_use: bool = False, replay_options: dict = None, dry_run: bool = False):
    """Handle LeRobot framework operations"""
    if dry_run:
        import json
        plan = {
            "action": "lerobot_operation",
            "mode": "train" if train else "record" if record else "inference" if inference else "replay" if replay else "teleop" if teleop else "motor_setup" if motors else "calibrate",
            "parameters": {
                "calibrate": calibrate,
                "motors": motors,
                "replay_options": replay_options
            },
            "status": "dry_run_plan_generated"
        }
        print(json.dumps(plan, indent=2))
        return

    # Import lerobot for operations that need it immediately at top level
    # Calibration and motor setup do lazy imports with loading spinners
    needs_lerobot = train or record or inference or replay or teleop
    
    if needs_lerobot:
        try:
            import lerobot  # Heavy import - only when needed
        except ImportError:
            typer.echo("❌ LeRobot is not installed.")
            return
    
    if train:
        # Training mode - train a policy on recorded data
        from solo.commands.robots.lerobot.modes import training_mode
        training_mode(config, auto_use)
    elif record:
        # Recording mode - check for existing calibration and setup recording
        from solo.commands.robots.lerobot.modes import recording_mode
        recording_mode(config, auto_use)
    elif inference:
        # Inference mode - run pretrained policy on robot
        from solo.commands.robots.lerobot.modes import inference_mode
        inference_mode(config, auto_use)
    elif replay:
        # Replay mode - replay actions from a recorded dataset episode
        from solo.commands.robots.lerobot.modes import replay_mode
        replay_mode(config, auto_use, replay_options)
    elif teleop:
        # Teleoperation mode - check for existing calibration
        teleop_mode(config, auto_use)
    elif motors is not None:
        # Motor setup mode - setup motor IDs only
        motor_setup_mode(config, motors)
    elif calibrate is not None:
        # Calibration mode - calibrate only 
        calibration_mode(config, calibrate)

def teleop_mode(config: dict, auto_use: bool = False):
    """Handle LeRobot teleoperation mode"""
    # Lazy import - only load when teleop is actually used
    from solo.commands.robots.lerobot.teleoperation import teleoperation

    # teleoperation() prints its own status messages (success/failure/stopped)
    teleoperation(config, auto_use)

def calibration_mode(config: dict, arm_type: str = None):
    """Handle LeRobot calibration mode"""
    # Lazy import - only load when calibration is actually used
    from solo.commands.robots.lerobot.calibration import calibration, check_calibration_success
    
    # calibration() saves config internally, no need to save again
    arm_config = calibration(config, arm_type)
    
    # Check calibration success using utility function
    check_calibration_success(arm_config, False)  # Motors already set up

def motor_setup_mode(config: dict, arm_type: str = None):
    """Handle LeRobot motor setup mode"""
    from solo.commands.robots.lerobot.calibration import setup_motors_for_arm, setup_motors_for_bimanual_arm
    from solo.commands.robots.lerobot.utils.preload import start_lerobot_preload
    from solo.commands.robots.lerobot.ports import detect_arm_port, detect_bimanual_arm_ports
    from solo.commands.robots.lerobot.config import save_lerobot_config, is_bimanual_robot
    from rich.prompt import Prompt, Confirm
    
    # Start loading heavy lerobot libraries in the background while user answers prompts
    start_lerobot_preload()
    
    typer.echo("🔧 Starting motor setup mode...")

    if arm_type is not None and arm_type not in ["leader", "follower", "all"]:
        raise ValueError(f"Invalid arm type: {arm_type}, please use 'leader', 'follower', or 'all'")
    
    # Gather any existing config and ask once to reuse
    lerobot_config = config.get('lerobot', {})
    existing_robot_type = lerobot_config.get('robot_type')
    existing_leader_port = lerobot_config.get('leader_port')
    existing_follower_port = lerobot_config.get('follower_port')
    existing_left_leader_port = lerobot_config.get('left_leader_port')
    existing_right_leader_port = lerobot_config.get('right_leader_port')
    existing_left_follower_port = lerobot_config.get('left_follower_port')
    existing_right_follower_port = lerobot_config.get('right_follower_port')
    
    reuse_all = False
    if existing_robot_type or existing_leader_port or existing_follower_port or existing_left_leader_port:
        typer.echo("\n📦 Found existing configuration:")
        if existing_robot_type:
            typer.echo(f"   • Robot type: {existing_robot_type}")
        
        # Show ports based on whether bimanual or not
        if existing_robot_type and is_bimanual_robot(existing_robot_type):
            if existing_left_leader_port:
                typer.echo(f"   • Left leader port: {existing_left_leader_port}")
            if existing_right_leader_port:
                typer.echo(f"   • Right leader port: {existing_right_leader_port}")
            if existing_left_follower_port:
                typer.echo(f"   • Left follower port: {existing_left_follower_port}")
            if existing_right_follower_port:
                typer.echo(f"   • Right follower port: {existing_right_follower_port}")
        else:
            # Only show relevant port(s) based on arm_type
            if arm_type == "leader" and existing_leader_port:
                typer.echo(f"   • Leader port: {existing_leader_port}")
            elif arm_type == "follower" and existing_follower_port:
                typer.echo(f"   • Follower port: {existing_follower_port}")
            elif arm_type not in ["leader", "follower"]:
                if existing_leader_port:
                    typer.echo(f"   • Leader port: {existing_leader_port}")
                if existing_follower_port:
                    typer.echo(f"   • Follower port: {existing_follower_port}")
        reuse_all = Confirm.ask("Use these settings?", default=True)
    
    if reuse_all and existing_robot_type:
        robot_type = existing_robot_type
    else:
        # Manual selection of robot type
        from solo.commands.robots.lerobot.utils.helper import prompt_robot_type_selection
        robot_type = prompt_robot_type_selection(default="so101")
    
    motor_config = {'robot_type': robot_type}
    is_bimanual = is_bimanual_robot(robot_type)
    
    # Check if RealMan robot (uses network connection for follower)
    from solo.commands.robots.lerobot.config import is_realman_robot
    is_realman = is_realman_robot(robot_type)
    
    # Determine which arms to setup based on arm_type parameter
    if arm_type == "leader":
        setup_leader = True
        setup_follower = False
    elif arm_type == "follower":
        setup_leader = False
        setup_follower = True
    else:
        # arm_type is "all", setup both arms
        setup_leader = True
        setup_follower = True
    
    if is_realman:
        # RealMan robot setup workflow
        # Leader is SO101 (USB), Follower is RealMan (network)
        from solo.commands.robots.lerobot.realman_config import (
            load_realman_config,
            prompt_realman_config,
            save_realman_config,
            test_realman_connection,
        )
        
        if setup_leader:
            # Setup SO101 leader arm (USB)
            leader_port = existing_leader_port if reuse_all and existing_leader_port else None
            if not leader_port:
                typer.echo("\n📟 Setting up SO101 Leader Arm (USB)")
                leader_port, _ = detect_arm_port("leader", robot_type="so101")
            
            if not leader_port:
                typer.echo("❌ Failed to detect SO101 leader arm. Skipping leader setup.")
            else:
                motor_config['leader_port'] = leader_port
                save_lerobot_config(config, {'leader_port': leader_port})
                
                # Setup motor IDs for SO101 leader
                leader_motors_setup = setup_motors_for_arm("leader", leader_port, "so101")
                motor_config['leader_motors_setup'] = leader_motors_setup
        
        if setup_follower:
            # Setup RealMan follower arm (network)
            typer.echo("\n🤖 Setting up RealMan Follower Arm (Network)")
            typer.echo("   RealMan robots connect via IP address, not USB.")
            
            # Load existing config or prompt for new one
            lerobot_config = config.get('lerobot', {})
            existing_realman_config = lerobot_config.get('realman_config')
            
            if existing_realman_config and reuse_all:
                realman_config = existing_realman_config
                typer.echo(f"   Using existing config: {realman_config['ip']}:{realman_config['port']}")
            else:
                # Try to load from file first
                realman_config = load_realman_config()
                
                # Ask if user wants to modify
                if Confirm.ask("Would you like to modify RealMan settings?", default=False):
                    realman_config = prompt_realman_config(realman_config)
                    save_realman_config(realman_config)
            
            # Test connection
            if test_realman_connection(realman_config):
                motor_config['realman_config'] = realman_config
                motor_config['follower_motors_setup'] = True
                save_lerobot_config(config, {'realman_config': realman_config})
                typer.echo("✅ RealMan follower arm setup completed!")
            else:
                motor_config['follower_motors_setup'] = False
                typer.echo("❌ RealMan follower arm setup failed - check network connection.")
    
    elif is_bimanual:
        # Bimanual motor setup workflow
        if setup_leader:
            left_leader_port = existing_left_leader_port if reuse_all and existing_left_leader_port else None
            right_leader_port = existing_right_leader_port if reuse_all and existing_right_leader_port else None
            
            if not left_leader_port or not right_leader_port:
                left_leader_port, right_leader_port = detect_bimanual_arm_ports("leader")
            
            if not left_leader_port or not right_leader_port:
                typer.echo("❌ Failed to detect bimanual leader arms. Skipping leader setup.")
            else:
                motor_config['left_leader_port'] = left_leader_port
                motor_config['right_leader_port'] = right_leader_port
                save_lerobot_config(config, {
                    'left_leader_port': left_leader_port,
                    'right_leader_port': right_leader_port
                })
                
                # Setup motor IDs for bimanual leader arms
                leader_motors_setup = setup_motors_for_bimanual_arm("leader", left_leader_port, right_leader_port, robot_type)
                motor_config['leader_motors_setup'] = leader_motors_setup
        
        if setup_follower:
            left_follower_port = existing_left_follower_port if reuse_all and existing_left_follower_port else None
            right_follower_port = existing_right_follower_port if reuse_all and existing_right_follower_port else None
            
            if not left_follower_port or not right_follower_port:
                left_follower_port, right_follower_port = detect_bimanual_arm_ports("follower")
            
            if not left_follower_port or not right_follower_port:
                typer.echo("❌ Failed to detect bimanual follower arms. Skipping follower setup.")
            else:
                motor_config['left_follower_port'] = left_follower_port
                motor_config['right_follower_port'] = right_follower_port
                save_lerobot_config(config, {
                    'left_follower_port': left_follower_port,
                    'right_follower_port': right_follower_port
                })
                
                # Setup motor IDs for bimanual follower arms
                follower_motors_setup = setup_motors_for_bimanual_arm("follower", left_follower_port, right_follower_port, robot_type)
                motor_config['follower_motors_setup'] = follower_motors_setup
    
    else:
        # Single-arm motor setup workflow
        if setup_leader:
            # Use consolidated decision for leader port
            leader_port = existing_leader_port if reuse_all and existing_leader_port else None
            if not leader_port:
                leader_port, _ = detect_arm_port("leader", robot_type=robot_type)
            
            if not leader_port:
                typer.echo("❌ Failed to detect leader arm. Skipping leader setup.")
            else:
                motor_config['leader_port'] = leader_port
                # Save port to config immediately
                save_lerobot_config(config, {'leader_port': leader_port})
                
                # Setup motor IDs for leader arm
                leader_motors_setup = setup_motors_for_arm("leader", leader_port, robot_type)
                motor_config['leader_motors_setup'] = leader_motors_setup
        
        if setup_follower:
            # Use consolidated decision for follower port
            follower_port = existing_follower_port if reuse_all and existing_follower_port else None
            if not follower_port:
                follower_port, _ = detect_arm_port("follower", robot_type=robot_type)
            
            if not follower_port:
                typer.echo("❌ Failed to detect follower arm. Skipping follower setup.")
            else:
                motor_config['follower_port'] = follower_port
                # Save port to config immediately
                save_lerobot_config(config, {'follower_port': follower_port})
                
                # Setup motor IDs for follower arm
                follower_motors_setup = setup_motors_for_arm("follower", follower_port, robot_type)
                motor_config['follower_motors_setup'] = follower_motors_setup
    
    # Save final motor configuration
    save_lerobot_config(config, motor_config)
    
    # Report final status
    leader_setup = motor_config.get('leader_motors_setup', False)
    follower_setup = motor_config.get('follower_motors_setup', False)
    
    if (setup_leader and leader_setup) or (setup_follower and follower_setup):
        typer.echo("\n🔧 You can now run 'solo robo --calibrate all' to calibrate the arms.")
    else:
        typer.echo("\nRun 'solo robo --motors all' to retry.")