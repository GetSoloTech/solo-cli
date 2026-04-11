# Solo CLI

<div align="center">

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/license/apache-2-0)
[![PyPI Version](https://img.shields.io/pypi/v/solo-cli)](https://pypi.org/project/solo-cli/)
[![GitHub Clones](https://img.shields.io/badge/dynamic/json?color=success&label=Clones&query=count&url=https://gist.githubusercontent.com/zeeshaan/GIST_ID/raw/clones.json&logo=github)](https://github.com/GetSoloTech/solo-cli)
[![GitHub Views](https://img.shields.io/badge/dynamic/json?color=success&label=Views&query=count&url=https://gist.githubusercontent.com/zeeshaan/GIST_ID/raw/views.json&logo=github)](https://github.com/GetSoloTech/solo-cli)

**Fastest way to deploy Physical AI on your hardware**

Simple CLI for Physical AI:
*Fine-tune and serve models in the physical world; optimized for edge & on-device operations*

</div>

<p align="center">
  <img src="media/solo-banner.png" alt="Solo Tech" width="500">
</p>

---

Solo-CLI powers users of Physical AI Inference by providing access to efficiency tuned AI models in the real world. From language to vision to action models, Solo-CLI allows you to interact with cutting-edge, on-device AI directly within the terminal. It is tailored for context aware intelligence, specialized for mission-critical tasks, and tuned for the edge.

<p align="center">
  <a href="https://docs.getsolo.tech">Docs</a> |
  <a href="https://getsolo.tech">About</a>
</p>

<div align="center">
  <table>
    <tr>
      <td align="center"><img src="media/LeRobot_Chess.png" alt="LeRobot Chess Match Screenshot" title="LeRobot Chess Match" width="375" height="225"></td>
      <td align="center"><img src="media/LeRobot_Writer.png" alt="LeRobot Writer Screenshot" title="LeRobot Author" width="375" height="225"></td>
    </tr>
  </table>
</div>

## Installation

### Prerequisites

<details>
<summary><b>Git LFS</b> (required)</summary>

Solo-CLI depends on [solo-bot](https://github.com/GetSoloTech/solo-bot) which uses Git LFS. If you haven't installed it before:

```bash
# Mac
brew install git-lfs

# Ubuntu / Debian
sudo apt-get install git-lfs

# Windows (pick one)
winget install GitHub.GitLFS
```

Then run once:

```bash
git lfs install
```

</details>

<details>
<summary><b>uv package manager</b> (recommended)</summary>

```bash
# Mac & Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows Powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

</details>

### Setup

```bash
# Create and activate a uv virtual environment (Python 3.12 recommended)
uv venv --python 3.12
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

### Install

```bash
git clone https://github.com/GetSoloTech/solo-cli.git
cd solo-cli
uv pip install -e .
```


## Solo Commands:

```bash
solo --help

╭─ Commands ────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ setup      Set up Solo CLI environment with interactive prompts and saves configuration to config.json.           │
│ login      Authenticate with Solo Hub using device-code login flow.                                               │
│ whoami     Display current user profile, organization, and subscription info.                                     │
│ download   Download a model from Solo Hub (format: org/model_name or solo:org/model_name).                        │
│ robo       Robotics operations: motor setup, calibration, teleoperation, data recording, training, and inference  │
│ serve      Start a model server with the specified model.                                                         │
│ status     Check running models, system status, and configuration.                                                │
│ list       List all downloaded models available in HuggingFace cache and Ollama.                                  │
│ test       Test if the Solo CLI is running correctly. Performs an inference test to verify server functionality.  │
│ stop       Stops Solo CLI services. You can specify a server type with 'ollama', 'vllm', or 'llama.cpp'           │
│            Otherwise, all Solo services will be stopped.                                                          │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯


```

## Solo Hub - Authentication and Model Downloads

```bash
# Authenticate with Solo Hub
solo login

# Force re-authentication
solo login --force

# Check your profile and subscription
solo whoami

# Download a model from Solo Hub
solo download org/model_name

# Download to a specific local directory
solo download org/model_name --local-dir ./my-models
```

## Interactive CLI for Robots
**Find more details here: [Solo Robo Docs](solo/commands/robots/lerobot/README.md)**

```bash
# Calibrate -> Teleop
solo robo --calibrate all
solo robo --teleop

# Record a new local dataset with prompts
solo robo --record

# Train ACT or SmolVLA Policy on a recorded dataset and push to Hub
solo robo --train

# Inference with VLA
solo robo --inference

# Replay a recorded action/episode
solo robo --replay

# Use -y or --yes to auto-use saved settings (skip prompts)
solo robo --teleop -y
solo robo --record --yes
```


## Interactive CLI for Local AI Deployment

```bash

# Note that you will need Docker for solo serve
solo setup
solo serve --server ollama --model llama3.2:1b
```
## API Reference
Find more details here: OpenAI -> [OpenAI API Docs](https://platform.openai.com/docs/api-reference/introduction) Ollama -> [Ollama API Docs](https://docs.ollama.com/api)

### vLLM & llama.cpp (OpenAI Compatible)

```bash
# Chat request endpoint
curl http://localhost:5070/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.2",
    "messages": [{"role": "user", "content": "Analyze sensor data"}],
    "tools": [{"type": "mcp", "name": "VitalSignsMCP"}]
  }'
```

### Ollama
```bash
# Chat request endpoint
curl http://localhost:5070/api/chat -d '{
  "model": "llama3.2",
  "messages": [
    {
      "role": "user",
      "content": "why is the sky blue?"
    }
  ]
}'
```

## Configuration
Navigate to config file
`.solo/config.json`

```json
{
    "hardware": {
        "use_gpu": false,
        "cpu_model": "Apple M3",
        "cpu_cores": 8,
        "memory_gb": 16.0,
        "gpu_vendor": "None",
        "gpu_model": "None",
        "gpu_memory": 0,
        "compute_backend": "CPU",
        "os": "Darwin"
    },
    "user": {
        "domain": "Software",
        "role": "Full-Stack Developer"
    },
    "server": {
        "type": "ollama",
        "ollama": {
            "default_port": 5070
        }
    },
    "active_model": {
        "server": "ollama",
        "name": "llama3.2:1b",
        "full_model_name": "llama3.2:1b",
        "port": 5070,
        "last_used": "2025-10-09 11:30:06"
    }
}
```

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/name`)
3. Commit changes (`git commit -m 'Add feature'`)
4. Push to branch (`git push origin feature/name`)
5. Open Pull Request
