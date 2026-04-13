import json
from typer.testing import CliRunner
from solo.cli import app
from solo.state import state

runner = CliRunner()

def test_status_json_output():
    # Run the status command forcing json
    result = runner.invoke(app, ["status", "--output", "json"])
    assert result.exit_code == 0
    
    # Verify it parses correctly
    data = json.loads(result.stdout)
    assert "configuration" in data
    assert "services" in data
    assert isinstance(data["services"], list)

def test_list_json_output():
    # Run the list command forcing json
    result = runner.invoke(app, ["list", "--output", "json"])
    assert result.exit_code == 0
    
    # Verify it parses correctly
    data = json.loads(result.stdout)
    assert "huggingface_models" in data
    assert "ollama_models" in data
    assert isinstance(data["huggingface_models"], list)

def test_robo_dry_run():
    # Run a physical robotics command with --dry-run
    result = runner.invoke(app, ["robo", "--calibrate", "all", "--dry-run"])
    assert result.exit_code == 0
    
    # Under dry-run, motor config prompts are avoided and a plan is outputted
    data = json.loads(result.stdout)
    assert data["status"] == "dry_run_plan_generated"
    assert data["action"] == "lerobot_operation"
    assert data["mode"] == "calibrate"
    assert data["parameters"]["calibrate"] == "all"

def test_whoami_json_output():
    # whoami will fail auth in CI, but we must make sure the error comes back as JSON!
    result = runner.invoke(app, ["whoami", "--output", "json"])
    
    # Note: Even if it fails auth, the stdout should contain a JSON payload with an "error" key.
    data = json.loads(result.stdout)
    assert "error" in data or "name" in data
