# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Solo CLI is a Python CLI tool for Physical AI - enabling model inference on edge hardware, robotics operations (motor control, teleoperation, training), and model deployment via Ollama, vLLM, or llama.cpp servers. It also integrates with Solo Hub for authentication and model downloads.

## Development Setup

```bash
# Prerequisites: Git LFS, uv package manager
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
```

## Common Commands

```bash
# Run the CLI
solo

# Interactive setup (hardware detection, server config, saves to ~/.solo/config.json)
solo setup

# Linting/formatting (no config files - uses defaults)
black solo/
isort solo/

# Tests
pytest
```

## Architecture

**CLI Framework:** Typer with Rich for terminal UI. Entry point is `solo/cli.py`.

**Lazy-loaded commands:** All CLI commands in `solo/commands/` are imported inside function bodies in `cli.py` for startup performance. Follow this pattern when adding new commands.

**Key modules:**

- `solo/cli.py` - Typer command definitions (lazy imports from commands/)
- `solo/main.py` - Setup wizard logic (hardware detection, config generation)
- `solo/commands/` - Individual command implementations (serve, status, login, download, etc.)
- `solo/hub/` - Solo Hub integration (auth via device code flow, API client, model caching)
- `solo/utils/server_utils.py` - Server lifecycle management for Ollama/vLLM/llama.cpp (large file, ~1200 lines)
- `solo/utils/hardware.py` - Hardware detection (CPU, GPU - NVIDIA/AMD/Apple Silicon, memory)
- `solo/config/` - YAML defaults (`config.yaml`) + user JSON config (`~/.solo/config.json`)
- `solo/commands/robots/lerobot/` - LeRobot robotics integration (calibration, teleop, recording, training, inference)
- `solo/mcp/` - Domain-specific Model Context Protocol implementations (agriculture, education, healthcare, etc.)

**Multi-platform support:** Hardware detection and server selection adapt to CUDA (NVIDIA), HIP (AMD), Metal (Apple Silicon), and CPU-only environments.

**Configuration:** Two-tier system - YAML defaults in `solo/config/config.yaml`, user settings in `~/.solo/config.json`.
