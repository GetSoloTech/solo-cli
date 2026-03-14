"""
Pre-flight dependency and hardware checks for model inference.

Validates that required packages are installed and hardware is compatible
before attempting to load a policy model, providing clear guidance when
issues are detected.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import typer
from rich.prompt import Confirm

from solo.config import CONFIG_PATH

# Policy dependency registry
# Each required entry: (import_name, pip_spec)
# Each optional entry: (import_name, pip_spec, description)
POLICY_DEPS = {
    "groot": {
        "required": [
            ("transformers", "transformers>=4.57.1,<5.0.0"),
            ("timm", "timm>=1.0.0,<1.1.0"),
            ("safetensors", "safetensors>=0.4.3,<1.0.0"),
            ("PIL", "Pillow>=10.0.0,<13.0.0"),
            ("dm_tree", "dm-tree>=0.1.8,<1.0.0"),
            ("flash_attn", "flash-attn>=2.5.9,<3.0.0"),
        ],
        "optional": [
            ("peft", "peft>=0.13.0,<1.0.0", "LoRA fine-tuning support"),
        ],
        "requires_cuda": True,
        # flash-attn compiles from source and can take 10-20 minutes
        "slow_install_packages": ["flash-attn"],
    },
    "pi05": {
        "required": [
            ("transformers", "transformers>=4.57.1,<5.0.0"),
        ],
    },
    "pi0": {
        "required": [
            ("transformers", "transformers>=4.57.1,<5.0.0"),
        ],
    },
    "smolvla": {
        "required": [
            ("transformers", "transformers>=4.57.1,<5.0.0"),
            ("num2words", "num2words>=0.5.14,<0.6.0"),
            ("accelerate", "accelerate>=1.7.0,<2.0.0"),
            ("safetensors", "safetensors>=0.4.3,<1.0.0"),
        ],
    },
    "act": {"required": []},
    "diffusion": {"required": []},
}


def _read_config_json(filepath: str | Path) -> dict | None:
    """Read and parse a config.json file. Returns None on failure."""
    try:
        with open(filepath) as f:
            return json.load(f)
    except Exception:
        return None


def read_policy_type(policy_path: str) -> str | None:
    """Read the policy type from a model's config.json.

    Supports local paths, solo: prefixed paths, and HuggingFace repo IDs.
    Returns None on any failure (graceful skip).
    """
    try:
        config_data = None

        # Local path
        local = Path(policy_path.removeprefix("solo:")).expanduser()
        if local.is_dir():
            config_data = _read_config_json(local / "config.json")

        # Solo Hub model - try cache first, then download
        elif policy_path.startswith("solo:"):
            clean_id = policy_path.removeprefix("solo:")
            parts = clean_id.split("/", 1)

            # Try reading directly from Solo Hub cache
            if len(parts) == 2:
                from solo.hub.constants import REPO_ID_SEPARATOR, SOLO_CACHE_DIR

                org, model_name = parts
                cache_config = (
                    Path(SOLO_CACHE_DIR)
                    / f"models{REPO_ID_SEPARATOR}{org}{REPO_ID_SEPARATOR}{model_name}"
                    / "snapshots"
                    / "latest"
                    / "config.json"
                )
                config_data = _read_config_json(cache_config)

            # Fallback: download config.json via Solo Hub API
            if not config_data:
                from solo.hub import solo_hub_download

                downloaded = solo_hub_download(
                    repo_id=clean_id,
                    filename="config.json",
                )
                config_data = _read_config_json(downloaded)

        # HuggingFace model
        else:
            from huggingface_hub import hf_hub_download

            downloaded = hf_hub_download(
                repo_id=policy_path,
                filename="config.json",
            )
            config_data = _read_config_json(downloaded)

        if config_data and "type" in config_data:
            return config_data["type"]

    except Exception:
        pass

    return None


def check_dependencies(policy_type: str) -> tuple[list[str], list[str]]:
    """Check if required packages for a policy type are installed.

    Returns (missing_required_pip_specs, missing_optional_pip_specs).
    """
    deps = POLICY_DEPS.get(policy_type, {})
    missing_required = []
    missing_optional = []

    for import_name, pip_spec in deps.get("required", []):
        if not importlib.util.find_spec(import_name):
            missing_required.append(pip_spec)

    for entry in deps.get("optional", []):
        import_name, pip_spec = entry[0], entry[1]
        if not importlib.util.find_spec(import_name):
            missing_optional.append(pip_spec)

    return missing_required, missing_optional


def check_hardware_compatibility(policy_type: str) -> tuple[bool, str | None]:
    """Check if hardware is compatible with the policy.

    Returns (is_compatible, error_message).
    """
    deps = POLICY_DEPS.get(policy_type, {})

    if not deps.get("requires_cuda", False):
        return True, None

    try:
        from solo.utils.hardware import detect_hardware

        _, _, _, _, gpu_model, _, compute_backend, _ = detect_hardware()

        if compute_backend == "CUDA":
            return True, None

        hw_name = gpu_model if gpu_model != "None" else compute_backend
        return False, (
            f"This model requires an NVIDIA GPU with CUDA support.\n"
            f"   Your system uses {hw_name} which is not compatible.\n"
            f"   Flash Attention (required by Groot) only works on CUDA devices."
        )
    except Exception:
        # If hardware detection fails, don't block
        return True, None


def _get_installer_cmd() -> list[str]:
    """Get the pip/uv install command based on user config."""
    # Check saved config
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                config = json.load(f)
            pkg_manager = config.get("environment", {}).get("package_manager")
            if pkg_manager == "uv":
                return ["uv", "pip", "install"]
    except Exception:
        pass

    # Check if uv is available
    try:
        result = subprocess.run(
            ["uv", "--version"], check=False, capture_output=True
        )
        if result.returncode == 0:
            return ["uv", "pip", "install"]
    except FileNotFoundError:
        pass

    return [sys.executable, "-m", "pip", "install"]


def _install_packages(pip_specs: list[str]) -> bool:
    """Install packages using pip or uv. Returns True on success."""
    installer_cmd = _get_installer_cmd()
    cmd = installer_cmd + pip_specs

    installer_name = "uv" if "uv" in installer_cmd else "pip"
    typer.echo(f"\n   Installing with {installer_name}...")

    try:
        subprocess.check_call(cmd)
        typer.echo("   Packages installed successfully.")
        return True
    except subprocess.CalledProcessError:
        typer.echo("   Failed to install packages.")
        typer.echo(f"   Try manually: {' '.join(cmd)}")
        return False


def run_preflight_check(policy_path: str) -> bool:
    """Run pre-flight dependency and hardware checks before inference.

    Returns True if safe to proceed, False if inference should be aborted.
    Skips gracefully for unknown policy types or unreadable configs.
    """
    typer.echo("\nChecking model requirements...")

    # Read policy type
    policy_type = read_policy_type(policy_path)
    if not policy_type:
        # Can't determine type - skip check, let existing error handling work
        return True

    typer.echo(f"   Policy type: {policy_type}")

    if policy_type not in POLICY_DEPS:
        # Unknown policy type - skip check
        return True

    # Hardware check first
    is_compatible, hw_error = check_hardware_compatibility(policy_type)
    if not is_compatible:
        typer.echo(f"\n   {hw_error}")
        return False

    # Dependency check
    missing_required, missing_optional = check_dependencies(policy_type)

    if not missing_required and not missing_optional:
        typer.echo("   All requirements satisfied.\n")
        return True

    # Show missing packages
    if missing_required:
        names = [spec.split(">=")[0].split("==")[0] for spec in missing_required]
        typer.echo(f"\n   Missing packages: {', '.join(names)}")

    if missing_optional:
        names = [spec.split(">=")[0].split("==")[0] for spec in missing_optional]
        typer.echo(f"   Optional (not installed): {', '.join(names)}")

    # Warn about slow-installing packages (e.g., flash-attn compiles from source)
    slow_packages = deps.get("slow_install_packages", [])
    all_missing_names = [spec.split(">=")[0].split("==")[0] for spec in missing_required + missing_optional]
    slow_missing = [pkg for pkg in slow_packages if pkg in all_missing_names]
    if slow_missing:
        typer.echo(f"\n   Note: {', '.join(slow_missing)} compiles from source and may take 10-20 minutes to install.")

    # Prompt to install
    all_missing = missing_required + missing_optional
    if Confirm.ask("\n   Install required packages?", default=True):
        if _install_packages(all_missing):
            return True
        return False

    if missing_required:
        typer.echo("   Cannot proceed without required packages.")
        return False

    # Only optional missing - can proceed
    return True
