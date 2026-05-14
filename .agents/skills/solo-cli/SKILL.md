---
name: solo-cli
description: Operate the Solo CLI for local Physical AI workflows. Use when Codex needs to install or run `solo`, authenticate with Solo Hub, download models, serve local inference with Ollama/vLLM/llama.cpp, inspect Solo status, stop Solo services, or guide/run LeRobot robotics workflows such as USB setup, motor setup, calibration, teleoperation, recording, replay, training, and inference.
---

# Solo CLI

## Workflow

Use this skill to operate Solo CLI from a repository checkout or an installed `solo` command.

1. Run the Solo environment precheck before any Solo command:
   - Confirm a Python virtual environment is active: `test -n "$VIRTUAL_ENV"`.
   - Confirm this project is installed in that environment: `python -m pip show solo-cli` or `python -c "import solo"`.
   - Confirm the CLI is available: `solo --help`.
   - If `solo` is not on `PATH`, try `python -m solo.cli --help` only after the virtual environment and project install checks pass.
2. If any precheck condition is not met, stop and inform the user that they need the necessary setup before using Solo commands. Tell them to create/activate a Python virtual environment and install this project first:
   ```bash
   uv venv --python 3.12
   source .venv/bin/activate
   uv pip install -e .
   solo --help
   ```
3. For commands that touch hardware, authentication, paid services, remote uploads, or long-running training, explain the next command and wait for the user's explicit go-ahead unless they already asked you to execute it.
4. Use saved settings with `--yes` or `-y` only when the user asks for unattended execution or confirms the saved config is correct.
5. After running a server or robotics command, verify with the relevant status command (`solo status`, `solo test`, `docker ps`, `ollama list`, or the command's own output).
6. For detailed command options and robotics flow notes, read `references/command-guide.md`.

## Environment Precheck

Before using any commands in this skill, verify that the user is operating inside a Python virtual environment with this checkout installed. Run:

```bash
test -n "$VIRTUAL_ENV" && python -m pip show solo-cli && solo --help
```

If that fails, do not continue with Solo CLI operations. Explain that Solo commands require an active Python virtual environment with this project installed, and provide the install-from-checkout commands above.

## Common Tasks

- Install from this checkout:
  ```bash
  uv venv --python 3.12
  source .venv/bin/activate
  uv pip install -e .
  solo --help
  ```

- Set up Solo configuration:
  ```bash
  solo setup
  solo status
  ```

- Authenticate and download a Solo Hub model:
  ```bash
  solo login
  solo whoami
  solo download org/model_name
  ```

- Serve and test a local model:
  ```bash
  solo serve --server ollama --model llama3.2:1b
  solo test
  solo status
  ```

- Stop services:
  ```bash
  solo stop
  solo stop ollama
  ```

- Start the LeRobot workflow:
  ```bash
  solo setup-usb
  solo robo --scan
  solo robo --calibrate all
  solo robo --teleop
  ```

## Operating Rules

- Treat `solo setup`, `solo login`, `solo robo --record`, `solo robo --train`, `solo robo --inference`, and Hub uploads as interactive unless proven otherwise.
- Before robotics motion (`--calibrate`, `--teleop`, `--replay`, `--inference`), remind the user to clear the workspace, power the robot appropriately, and be ready to stop with Ctrl+C.
- Use `solo robo --scan` and `solo robo --diagnose` for connection issues before changing motor IDs.
- Use `solo robo --motors all|leader|follower` only for missing or incorrect motor IDs.
- Prefer local dataset names like `local/<name>` when the user does not explicitly want to push to HuggingFace Hub.
- Preserve existing `.solo/config.json`, `.env`, datasets, checkpoints, and model caches unless the user explicitly asks to reset or delete them.
