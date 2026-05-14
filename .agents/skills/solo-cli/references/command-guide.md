# Solo CLI Command Guide

Use this reference after the `solo-cli` skill triggers and the user asks for command-level help or execution.

## Core Commands

| Task | Command | Notes |
| --- | --- | --- |
| Show help | `solo --help` | Confirm installed command surface. |
| Configure environment | `solo setup` | Interactive. Saves Solo configuration and HuggingFace credentials. |
| Log in to Solo Hub | `solo login` | Device-code authentication. Use `--force` to re-authenticate. |
| Log out | `solo logout` | Removes stored Solo Hub credentials. |
| Show account | `solo whoami` | Displays profile, organization, and subscription info. |
| Download model | `solo download org/model_name` | Also accepts `solo:org/model_name`; requires Solo Hub login. |
| Download to directory | `solo download org/model_name --local-dir ./models` | Stores outside normal cache. |
| Serve model | `solo serve --server ollama --model llama3.2:1b` | Server choices: `ollama`, `vllm`, `llama.cpp`. |
| Serve on port | `solo serve --server vllm --model meta-llama/Llama-3.2-1B-Instruct --port 5070` | Docker may be required. |
| Inspect status | `solo status` | Shows config and running services. |
| Model training status | `solo status org/model_name` | Checks Solo Hub status for a model identifier. |
| List local models | `solo list` | Searches HuggingFace cache and Ollama. |
| Test inference | `solo test` | Use `--timeout` for slow models. |
| Stop all services | `solo stop` | Stops Solo services. |
| Stop one service | `solo stop ollama` | Also supports `vllm` and `llama.cpp`. |
| USB permissions | `solo setup-usb` | Linux installs udev/dialout config; macOS checks devices and drivers. |

## Install From Repo

Use this when working from a Solo CLI checkout:

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
solo --help
```

If `uv` is unavailable, create a Python 3.12 virtual environment with the standard library and install editable:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Git LFS is required because the package depends on `solo-bot`:

```bash
git lfs install
```

## Serving Models

Run `solo setup` before first serve so hardware and default server config exist.

```bash
solo serve --server ollama --model llama3.2:1b
solo serve --server vllm --model meta-llama/Llama-3.2-1B-Instruct
solo serve --server llama.cpp --model /path/to/model.gguf
```

Defaults:

- vLLM and llama.cpp normally use OpenAI-compatible endpoints on port `5070`.
- Native Ollama may use port `11434`; Docker-backed Solo Ollama may use port `5070`.
- Use `solo status` to confirm the actual URL.

Smoke tests:

```bash
solo test
curl http://localhost:5070/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"llama3.2","messages":[{"role":"user","content":"hello"}]}'
curl http://localhost:5070/api/chat -d '{"model":"llama3.2","messages":[{"role":"user","content":"hello"}]}'
```

## Robotics Command Map

Run robotics commands through `solo robo`. Most flows are interactive and save settings for later reuse.

| Task | Command | When to use |
| --- | --- | --- |
| Scan motors | `solo robo --scan` | First check for connected motors and ports. |
| Diagnose ports | `solo robo --diagnose` | Use for connection failures or ambiguous ports. |
| Setup motor IDs | `solo robo --motors all` | Only if IDs are missing or incorrect. Also accepts `leader` or `follower`. |
| Calibrate arms | `solo robo --calibrate all` | Required before teleop, record, and most motion workflows. Also accepts `leader` or `follower`. |
| Experimental autocalibration | `solo robo --auto-calibrate all` | Seeded SO101 autocalibration; treat as experimental. |
| Teleoperate | `solo robo --teleop` | Move follower with leader after calibration. |
| Record dataset | `solo robo --record` | Records demonstrations for training. |
| Replay episode | `solo robo --replay` | Replays a recorded dataset episode on follower. |
| Replay non-interactive | `solo robo --replay --dataset local/my_dataset --episode 0 --follower-id follower_right --fps 30` | Use when dataset, episode, follower ID, and FPS are known. |
| Train policy | `solo robo --train` | Trains ACT, SmolVLA, PI0, TDMPC, or diffusion policy on a dataset. |
| Run policy inference | `solo robo --inference` | Runs trained policy on follower. |

Add `--yes` or `-y` to reuse saved settings:

```bash
solo robo --teleop -y
solo robo --record --yes
solo robo --train -y
solo robo --inference --yes
solo robo --replay -y
```

## Robotics Safety And Sequencing

Recommended first-time sequence:

```bash
solo setup-usb
solo robo --scan
solo robo --diagnose
solo robo --calibrate all
solo robo --teleop
solo robo --record
solo robo --replay
solo robo --train
solo robo --inference
```

Use this shorter sequence when motor IDs are already correct:

```bash
solo robo --calibrate all
solo robo --teleop
solo robo --record
```

During recording:

- Right Arrow: early stop/reset and move to next episode.
- Left Arrow: cancel current episode and re-record.
- Escape: stop session, encode videos, and upload if enabled.

Before any robot motion:

- Clear the robot workspace.
- Confirm the robot is powered and physically stable.
- Keep the terminal focused so Ctrl+C can stop the process.
- For RealMan setups, verify network connectivity and power before starting motion.

## Troubleshooting

- Missing config: run `solo setup`.
- `solo` command missing: activate the virtual environment or install with `uv pip install -e .`.
- Docker errors with vLLM or Docker-backed Ollama: start Docker Desktop, then rerun `solo serve`.
- Native Ollama port confusion: run `solo status`; native Ollama usually reports `http://localhost:11434`.
- Robot not found: run `solo setup-usb`, reconnect USB, then `solo robo --scan` and `solo robo --diagnose`.
- Wrong motor IDs: use `solo robo --motors leader`, `solo robo --motors follower`, or `solo robo --motors all`.
- Port changed during robotics workflow: rerun the same command; Solo often redetects and retries once.
