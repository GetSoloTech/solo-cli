# Solo Server

<div align="center">

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![PyPI Version](https://img.shields.io/pypi/v/solo-server)](https://pypi.org/project/solo-server/)

**Fastest way to deploy physical AI**

CLI for Solo-Server:
*Serving models in the physical world; optimized for on-device operation*

</div>

<div align="center">
  <table>
    <tr>
      <td align="center"><img src="media/LeRobot_Chess.png" alt="LeRobot Chess Match Screenshot" title="LeRobot Chess Match" width="375" height="225"></td>
      <td align="center"><img src="media/LeRobot_Writer.png" alt="LeRobot Writer Screenshot" title="LeRobot Author" width="375" height="225"></td>
    </tr>
  </table>
</div>

## Installation
First, install the uv package manager and setup a virtual environment as 
explained in [prereq.md](prereq.md)

```bash

#Choose one of the following for solo-server installation
#1. Install solo server from PyPI python manager
uv pip install solo-server

#2. Install solo server from source
git clone https://github.com/GetSoloTech/solo-server.git
cd solo-server
uv pip install -e .

# Solo commands
solo --help

```

<details>
<summary><strong>Video: Solo Tech Installation</strong></summary>

[![Video: Solo Tech Installation](media/SoloTechInstallThumbnail.png)](https://youtu.be/x2pVuYr08vk)

</details>

## Quick Installation for Mac (Automated)

For Mac users, we provide an automated installation script that handles all the setup steps:

```bash
# Clone the repository
git clone https://github.com/GetSoloTech/solo-server.git
cd solo-server

# Make the installation script executable
chmod +x install_mac.sh

# Run the automated installation
./install_mac.sh
```

The script will automatically:
- Install uv package manager (version 0.9.3)
- Create a virtual environment with Python 3.12.12
- Set up environment variables for dependencies
- Install solo-server in development mode with fallback handling for mujoco dependencies

After installation, activate the virtual environment:
```bash
source solo_venv/bin/activate
```

<details>
<summary><strong>Video: quickstart installation</strong></summary>

[![Video: Mac Quickstart Installation](media/MacQuickInstallThumbnail.png)](https://youtu.be/bGjaIfKvyAA)

</details>

## Quick İnstallation for Windows (Automated):
For Windows users, we provide an automated installation script that handles all the setup steps:
```
# Clone the repository
git clone https://github.com/GetSoloTech/solo-server.git
cd solo-server

# Run the automated installation
powershell -ExecutionPolicy Bypass -File .\install_windows.ps1

# After installation, activate the virtual environment:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\solo_venv\Scripts\Activate.ps1

# Then verify your setup
solo --help          
```

## Solo Commands:

```bash
solo --help
                                                                                                           
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ setup      Set up Solo Server environment with interactive prompts and saves configuration to config.json.           │
│ robo       Robotics operations: motor setup, calibration, teleoperation, data recording, training, and inference     │
│ serve      Start a model server with the specified model.                                                            │
│ status     Check running models, system status, and configuration.                                                   │
│ list       List all downloaded models available in HuggingFace cache and Ollama.                                     │
│ test       Test if the Solo server is running correctly. Performs an inference test to verify server functionality.  │
│ stop       Stops Solo Server services. You can specify a server type with 'ollama', 'vllm', or 'llama.cpp'           │
│            Otherwise, all Solo services will be stopped.                                                             │
│ download   Downloads a Hugging Face model using the huggingface repo id.                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

```
## Start server with SML models

```bash

# Note that you will need Docker for solo serve
solo setup
solo serve --server ollama --model llama3.2:1b
```

## Interactive Lerobot With Solo Server
Find more details here: [Solo Robo Documentation](solo_server/commands/robots/lerobot/README.md) 

```bash
# Motors (both) → Calibrate (both) → Teleop
solo robo --type lerobot --motors both
solo robo --type lerobot --calibrate both
solo robo --type lerobot --teleop

# Record a new local dataset with prompts
solo robo --type lerobot --record

# Train Diffusion Policy on a recorded dataset and push to Hub
solo robo --type lerobot --train

# Inference with a hub model id (with optional Teleop override)
solo robo --type lerobot --inference
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
`.solo_server/config.json` 

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
