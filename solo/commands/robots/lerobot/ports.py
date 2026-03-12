"""
Port detection utilities for LeRobot
"""

import platform
import subprocess
import threading
import time
from pathlib import Path
from typing import List, Optional
import typer
from rich.prompt import Prompt


def _input_with_timeout(timeout: float = None) -> bool:
    """
    Wait for user to press Enter, with an optional timeout.

    Returns True if Enter was pressed, False if timed out.
    If timeout is None, waits indefinitely (regular input behavior).
    """
    if timeout is None:
        input()
        return True

    received = threading.Event()

    def wait_for_input():
        try:
            input()
            received.set()
        except EOFError:
            pass

    thread = threading.Thread(target=wait_for_input, daemon=True)
    thread.start()

    return received.wait(timeout)


def find_available_ports() -> List[str]:
    """Find all available serial ports on the system.
    
    Returns ports specific to robot arm connections:
    - Linux: /dev/ttyACM*, /dev/ttyUSB*
    - macOS: /dev/tty.usbmodem*, /dev/tty.usbserial*, etc.
    - Windows: COM ports via pyserial
    """
    try:
        # Use the comprehensive port detection from scan.py
        from solo.commands.robots.lerobot.scan import get_serial_ports
        return get_serial_ports()
    except ImportError:
        # Fallback to basic detection
        try:
            from serial.tools import list_ports
            
            if platform.system() == "Windows":
                ports = [port.device for port in list_ports.comports()]
            elif platform.system() == "Darwin":  # macOS
                # Look for USB modem/serial devices
                ports = []
                for pattern in ["tty.usbmodem*", "tty.usbserial*", "cu.usbmodem*", "cu.usbserial*"]:
                    ports.extend(str(p) for p in Path("/dev").glob(pattern))
            else:  # Linux
                ports = []
                for pattern in ["ttyACM*", "ttyUSB*"]:
                    ports.extend(str(p) for p in Path("/dev").glob(pattern))
            return sorted(set(ports))
        except ImportError:
            typer.echo("❌ pyserial is required for port detection. Installing...")
            try:
                subprocess.run(["pip", "install", "pyserial"], check=True)
                from serial.tools import list_ports
                if platform.system() == "Windows":
                    return [port.device for port in list_ports.comports()]
                else:
                    ports = []
                    patterns = ["ttyACM*", "ttyUSB*"] if platform.system() != "Darwin" else ["tty.usbmodem*", "tty.usbserial*"]
                    for pattern in patterns:
                        ports.extend(str(p) for p in Path("/dev").glob(pattern))
                    return sorted(ports)
            except Exception as e:
                typer.echo(f"❌ Failed to install pyserial: {e}")
                return []


def detect_arm_port(arm_type: str, robot_type: str = None, use_auto_detect: bool = True, timeout: float = None) -> tuple[Optional[str], Optional[str]]:
    """
    Detect the port for a specific arm (leader or follower)
    
    First tries auto-detection based on motor types.
    Falls back to manual plug/unplug detection if auto-detection fails.
    
    Returns (detected_port, detected_robot_type) tuple
    """
    detected_robot_type = robot_type
    
    # Try auto-detection first (for all robot types)
    if use_auto_detect:
        typer.echo(f"\n🔍 Auto-detecting {arm_type} arm port...")
        try:
            from solo.commands.robots.lerobot.scan import auto_detect_single_port
            port, auto_robot_type = auto_detect_single_port(arm_type, robot_type, verbose=True)
            if port:
                # Update robot type if auto-detected
                if auto_robot_type and detected_robot_type is None:
                    detected_robot_type = auto_robot_type
                return port, detected_robot_type
            typer.echo("   Falling back to manual detection...")
        except Exception as e:
            typer.echo(f"   Auto-detection failed: {e}")
            typer.echo("   Falling back to manual detection...")
    
    # Manual detection via plug/unplug
    typer.echo(f"\n🔍 Detecting port for {arm_type} arm...")
    
    # Get initial ports
    ports_before = find_available_ports()
    typer.echo(f"Available ports: {ports_before}")
    
    # Ask user to plug in the arm
    if timeout:
        typer.echo(f"\n📱 Please plug in your {arm_type} arm and press Enter when connected. (timeout: {int(timeout)}s)")
    else:
        typer.echo(f"\n📱 Please plug in your {arm_type} arm and press Enter when connected.")
    if not _input_with_timeout(timeout):
        typer.echo(f"\n⏰ Timed out waiting for {arm_type} arm connection.")
        return None, detected_robot_type

    time.sleep(1.0)  # Allow time for port to be detected
    
    # Get ports after connection
    ports_after = find_available_ports()
    new_ports = list(set(ports_after) - set(ports_before))
    
    if len(new_ports) == 1:
        port = new_ports[0]
        typer.echo(f"✅ Detected {arm_type} arm on port: {port}")
        # Try to detect robot type from the newly connected port
        if detected_robot_type is None:
            try:
                from solo.commands.robots.lerobot.scan import detect_robot_type_from_port
                auto_robot_type, _, _ = detect_robot_type_from_port(port, verbose=True)
                if auto_robot_type:
                    detected_robot_type = auto_robot_type
            except Exception:
                pass
        return port, detected_robot_type
    elif len(new_ports) == 0:
        # If no new ports detected but there are existing ports,
        # the arm might already be connected. Try unplug/replug method.
        if len(ports_before) > 0:
            typer.echo(f"⚠️  No new port detected. The {arm_type} arm might already be connected.")
            typer.echo(f"Let's identify the correct port by unplugging and replugging.")
            
            # Ask user to unplug the arm
            if timeout:
                typer.echo(f"\n📱 Please UNPLUG your {arm_type} arm and press Enter when disconnected. (timeout: {int(timeout)}s)")
            else:
                typer.echo(f"\n📱 Please UNPLUG your {arm_type} arm and press Enter when disconnected.")
            if not _input_with_timeout(timeout):
                typer.echo(f"\n⏰ Timed out waiting for {arm_type} arm disconnection.")
                return None, detected_robot_type

            time.sleep(1.0)  # Allow time for port to be released
            
            # Get ports after disconnection
            ports_unplugged = find_available_ports()
            missing_ports = list(set(ports_before) - set(ports_unplugged))
            
            if len(missing_ports) == 1:
                # Found the port that disappeared
                port = missing_ports[0]
                typer.echo(f"✅ Identified {arm_type} arm port: {port}")
                typer.echo(f"📱 Please plug your {arm_type} arm back in and press Enter.")
                if not _input_with_timeout(timeout):
                    typer.echo(f"\n⏰ Timed out waiting for {arm_type} arm reconnection.")
                    return None, detected_robot_type
                time.sleep(1.0)  # Allow time for reconnection
                # Try to detect robot type
                if detected_robot_type is None:
                    try:
                        from solo.commands.robots.lerobot.scan import detect_robot_type_from_port
                        auto_robot_type, _, _ = detect_robot_type_from_port(port, verbose=True)
                        if auto_robot_type:
                            detected_robot_type = auto_robot_type
                    except Exception:
                        pass
                return port, detected_robot_type
            elif len(missing_ports) == 0:
                typer.echo(f"❌ No port disappeared when unplugging {arm_type} arm. Please check connection.")
                return None, detected_robot_type
            else:
                typer.echo(f"⚠️  Multiple ports disappeared: {missing_ports}")
                typer.echo("Please select which port corresponds to your arm:")
                for i, port in enumerate(missing_ports, 1):
                    typer.echo(f"  {i}. {port}")
                
                choice = int(Prompt.ask("Enter port number", default="1"))
                if 1 <= choice <= len(missing_ports):
                    port = missing_ports[choice - 1]
                    typer.echo(f"📱 Please plug your {arm_type} arm back in and press Enter.")
                    if not _input_with_timeout(timeout):
                        typer.echo(f"\n⏰ Timed out waiting for {arm_type} arm reconnection.")
                        return None, detected_robot_type
                    time.sleep(1.0)
                    return port, detected_robot_type
                else:
                    port = missing_ports[0]
                    typer.echo(f"📱 Please plug your {arm_type} arm back in and press Enter.")
                    if not _input_with_timeout(timeout):
                        typer.echo(f"\n⏰ Timed out waiting for {arm_type} arm reconnection.")
                        return None, detected_robot_type
                    time.sleep(1.0)
                    return port, detected_robot_type
        else:
            typer.echo(f"❌ No ports available and no new port detected for {arm_type} arm. Please check connection.")
            return None, detected_robot_type
    else:
        typer.echo(f"⚠️  Multiple new ports detected: {new_ports}")
        typer.echo("Please select the correct port:")
        for i, port in enumerate(new_ports, 1):
            typer.echo(f"  {i}. {port}")
        
        choice = int(Prompt.ask("Enter port number", default="1"))
        if 1 <= choice <= len(new_ports):
            return new_ports[choice - 1], detected_robot_type
        else:
            return new_ports[0], detected_robot_type


def auto_detect_both_ports(robot_type: str = None) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Auto-detect both leader and follower ports based on motor types.
    Also auto-detects robot type if not specified.
    
    Returns (leader_port, follower_port, detected_robot_type).
    """
    try:
        from solo.commands.robots.lerobot.scan import auto_detect_ports
        return auto_detect_ports(robot_type, verbose=True)
    except Exception as e:
        typer.echo(f"⚠️  Auto-detection failed: {e}")
        return None, None, robot_type


def detect_bimanual_arm_ports(arm_type: str) -> tuple[Optional[str], Optional[str]]:
    """
    Detect ports for bimanual arm (left and right)
    Returns (left_port, right_port)
    """
    typer.echo(f"\n🔍 Detecting ports for bimanual {arm_type} arms...")
    typer.echo(f"⚠️  You'll need to connect TWO {arm_type} arms: LEFT and RIGHT")
    
    # Detect left arm
    typer.echo(f"\n👈 First, let's detect the LEFT {arm_type} arm...")
    left_port, _ = detect_arm_port(f"left {arm_type}")
    
    if not left_port:
        typer.echo(f"❌ Failed to detect left {arm_type} arm")
        return None, None
    
    # Detect right arm
    typer.echo(f"\n👉 Now, let's detect the RIGHT {arm_type} arm...")
    right_port, _ = detect_arm_port(f"right {arm_type}")
    
    if not right_port:
        typer.echo(f"❌ Failed to detect right {arm_type} arm")
        return left_port, None
    
    typer.echo(f"\n✅ Detected bimanual {arm_type} arms:")
    typer.echo(f"   • Left {arm_type}: {left_port}")
    typer.echo(f"   • Right {arm_type}: {right_port}")
    
    return left_port, right_port


def detect_and_retry_ports(leader_port: str, follower_port: str, config: dict = None) -> tuple[str, str]:
    """
    Detect new ports if connection fails and update config.
    Also updates all preconfigured mode settings (teleop, recording, inference, replay).
    
    Returns (new_leader_port, new_follower_port)
    """
    typer.echo("🔍 Detecting new ports...")
    
    # Detect new ports with a timeout so we don't hang forever on retry
    new_leader_port, _ = detect_arm_port("leader", timeout=30)
    new_follower_port, _ = detect_arm_port("follower", timeout=30)
    
    if new_leader_port and new_follower_port:
        typer.echo(f"✅ Found new ports:")
        typer.echo(f"   • Leader: {new_leader_port}")
        typer.echo(f"   • Follower: {new_follower_port}")
        
        # Update config with new ports if provided
        if config:
            from solo.commands.robots.lerobot.config import save_lerobot_config
            from solo.commands.robots.lerobot.mode_config import update_all_mode_config_ports
            
            # Update general config
            save_lerobot_config(config, {
                'leader_port': new_leader_port,
                'follower_port': new_follower_port
            })
            
            # Also update all preconfigured mode settings
            update_all_mode_config_ports(config, new_leader_port, new_follower_port)
        
        return new_leader_port, new_follower_port
    else:
        error_msg = "Could not detect new ports automatically."
        if leader_port is None:
            error_msg += " Leader port is not set."
        if follower_port is None:
            error_msg += " Follower port is not set."
        raise ValueError(error_msg) 