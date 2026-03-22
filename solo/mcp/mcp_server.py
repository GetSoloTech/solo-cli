import sys
import json
import subprocess
import asyncio

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("Error: The 'mcp' package is not installed. Please try reinstalling solo-cli.", file=sys.stderr)
    sys.exit(1)

mcp = FastMCP("Solo AI")

@mcp.tool()
def get_solo_status() -> str:
    \"\"\"Get the current status of the Solo CLI, including hardware configuration and running physical AI services.\"\"\"
    try:
        result = subprocess.check_output(["solo", "status", "--output", "json"], text=True)
        return result
    except subprocess.CalledProcessError as e:
        return f"Error getting status: {e.output or str(e)}"

@mcp.tool()
def list_downloaded_models() -> str:
    \"\"\"List all downloaded models available in HuggingFace cache and Ollama for physical AI tasks.\"\"\"
    try:
        result = subprocess.check_output(["solo", "list", "--output", "json"], text=True)
        return result
    except subprocess.CalledProcessError as e:
        return f"Error listing models: {e.output or str(e)}"

@mcp.tool()
def simulate_robot_action(action_type: str, arm: str = "all") -> str:
    \"\"\"
    Simulate a robotics action using LeRobot without actually moving physical hardware.
    action_type should be one of: 'teleop', 'record', 'calibrate', 'train', 'inference'.
    arm should be 'all', 'leader', or 'follower' (for calibrate only).
    \"\"\"
    valid_actions = ["teleop", "record", "calibrate", "train", "inference"]
    if action_type not in valid_actions:
        return json.dumps({"error": f"Invalid action_type. Must be one of {valid_actions}"})
    
    cmd = ["solo", "robo", f"--{action_type}"]
    if action_type == "calibrate":
        cmd.append(arm)
    cmd.append("--dry-run")
    
    try:
        result = subprocess.check_output(cmd, text=True)
        return result
    except subprocess.CalledProcessError as e:
        return f"Error simulating action: {e.output or str(e)}"


def start_mcp_server():
    \"\"\"Start the Model Context Protocol stdio server to integrate Solo CLI with AI Agents.\"\"\"
    mcp.run()

if __name__ == "__main__":
    start_mcp_server()
