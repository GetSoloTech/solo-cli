import os
import sys
import json
import typer
import subprocess
from enum import Enum
from pathlib import Path
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from solo.config import CONFIG_PATH
from solo.utils.hardware import hardware_info, is_ollama_natively_installed, check_ollama_service_status
from solo.utils.nvidia import is_cuda_toolkit_installed, check_nvidia_toolkit
from solo.config.config_loader import get_server_config, get_repository_config
from solo.utils.docker_utils import start_docker_engine

console = Console()

class Domain(str, Enum):
    PERSONAL = "Personal"
    EDUCATION = "Education"
    ROBOTICS = "Robotics"
    AGRICULTURE = "Agriculture"
    SOFTWARE = "Software"
    HEALTHCARE = "Healthcare"
    FORENSICS = "Forensics"
    ENTERPRISE = "Enterprise"
    CUSTOM = "Custom"

class ServerType(str, Enum):
    OLLAMA = "ollama"
    VLLM = "vllm"
    LLAMACPP = "llama.cpp"

def setup():
    """
    Set up the Solo CLI environment with interactive prompts and saves configuration to config.json.
    """
    from solo.state import state
    if state.get("non_interactive"):
        if not sys.stdin.isatty():
            try:
                stdin_data = json.load(sys.stdin)
                os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
                with open(CONFIG_PATH, 'w') as f:
                    json.dump(stdin_data, f, indent=4)
                if state.get("output_format") == "json":
                    print(json.dumps({"status": "setup_complete"}))
                else:
                    typer.echo("✅ Setup complete via stdin configuration.")
                return
            except Exception as e:
                if state.get("output_format") == "json":
                    print(json.dumps({"error": f"Failed to parse stdin: {e}"}))
                else:
                    typer.echo(f"❌ Error parsing stdin configuration: {e}")
                return

    typer.echo("💾 Setting up Solo CLI...")
    
    # Step 1: HuggingFace Authentication
    typer.echo("🔐 Step 1: HuggingFace Authentication")
    typer.echo("HuggingFace authentication is required for downloading models and datasets.")
    
    # Get HuggingFace username
    hf_username = Prompt.ask("Enter your HuggingFace username")
    
    # Get HuggingFace token
    typer.echo("You can get your token from: https://huggingface.co/settings/tokens")
    hf_token = typer.prompt("Enter your HuggingFace token", hide_input=True, show_default=False)
    
    # Create .env file with HuggingFace credentials
    env_path = Path(".env")
    env_content = f"""# HuggingFace Configuration
HUGGINGFACE_USERNAME={hf_username}
HUGGINGFACE_TOKEN={hf_token}
"""
    
    with open(env_path, 'w') as f:
        f.write(env_content)
    
    typer.echo(f"✅ HuggingFace credentials saved to {env_path}")
    
    # Check system info and display hardware info
    typer.echo("\n🔍 Step 2: Checking system information...\n")
    cpu_model, cpu_cores, memory_gb, gpu_vendor, gpu_model, gpu_memory, compute_backend, os_name = hardware_info(typer)
    
    # GPU Check and Configuration
    use_gpu = False
    if gpu_vendor != "None":
        typer.echo(f"\n🖥️  Detected GPU: {gpu_model} ({gpu_vendor})")
        
        # Check for proper GPU drivers/toolkit
        drivers_installed = False
        
        if gpu_vendor == "NVIDIA":
            drivers_installed = is_cuda_toolkit_installed() and check_nvidia_toolkit(os_name)
            
            if drivers_installed:
                typer.echo("✅ NVIDIA GPU drivers and toolkit are correctly installed.")
                use_gpu = Confirm.ask("Would you like to use GPU for inference?", default=True)
            else:
                typer.echo("❌ NVIDIA GPU drivers or toolkit are not properly installed.")
                install_drivers = Confirm.ask("Would you like to install the required drivers?", default=True)
                
                if install_drivers:
                    typer.echo("\n📥 Installing NVIDIA CUDA Toolkit...")
                    if os_name == "Windows":
                        # Open CUDA download page in browser
                        typer.echo("Opening NVIDIA CUDA Toolkit download page in your browser...")
                        subprocess.Popen(["start", "https://developer.nvidia.com/cuda-downloads"], shell=True)
                        typer.echo("Please follow the installation instructions and run 'solo setup' again after installation.")
                    elif os_name == "Linux":
                        typer.echo("For Linux, we recommend installing CUDA toolkit using package manager:")
                        typer.echo("  Ubuntu/Debian: sudo apt install nvidia-cuda-toolkit")
                        typer.echo("  CentOS/RHEL: sudo yum install cuda")
                        typer.echo("Please install the appropriate package and run 'solo setup' again.")
                    elif os_name == "Darwin":
                        typer.echo("macOS with NVIDIA GPUs is not fully supported. Please use CPU inference.")
                    
                    # Exit without completing setup
                    return
        
        elif gpu_vendor == "AMD":
            # Check for AMD drivers (ROCm)
            try:
                rocm_check = subprocess.run(["rocm-smi"], capture_output=True, text=True)
                drivers_installed = rocm_check.returncode == 0
            except FileNotFoundError:
                drivers_installed = False
            
            if drivers_installed:
                typer.echo("✅ AMD GPU drivers are correctly installed.")
                use_gpu = Confirm.ask("Would you like to use GPU for inference?", default=True)
            else:
                typer.echo("❌ AMD GPU drivers are not properly installed.")
                install_drivers = Confirm.ask("Would you like to install the required drivers?", default=True)
                
                if install_drivers:
                    typer.echo("\n📥 Installing AMD ROCm...")
                    if os_name == "Windows":
                        typer.echo("Opening AMD ROCm download page in your browser...")
                        subprocess.Popen(["start", "https://www.amd.com/en/graphics/servers-solutions-rocm"], shell=True)
                    elif os_name == "Linux":
                        typer.echo("For Linux, please follow AMD's ROCm installation guide:")
                        typer.echo("  https://docs.amd.com/en/latest/deploy/linux/index.html")
                    typer.echo("Please follow the installation instructions and run 'solo setup' again after installation.")
                    
                    # Exit without completing setup
                    return
        
        elif gpu_vendor == "Apple":
            typer.echo("✅ Apple Silicon GPU detected. Using built-in Metal acceleration.")
            use_gpu = True
    else:
        typer.echo("\n⚠️  No GPU detected. Using CPU for inference.")
    
    # Domain Selection
    typer.echo("\n🏢 Step 3: Choose the domain that best describes your field:") 
    console = Console()
    domain_table = Table()
    domain_table.add_column("ID", style="cyan", justify="center")
    domain_table.add_column("Domain", style="green")
    
    for i, domain in enumerate(Domain, 1):
        domain_table.add_row(str(i), domain.value)
    
    console.print(domain_table)
    
    domain_choice = int(Prompt.ask("Enter your domain ID", default="1"))
    domain = list(Domain)[domain_choice - 1] if 1 <= domain_choice <= len(Domain) else Domain.PERSONAL
    
    # If custom domain, ask for specific domain
    custom_domain = None
    if domain == Domain.CUSTOM:
        custom_domain = Prompt.ask("Enter your custom domain")
    
    # Server Selection
    typer.echo("\n🖥️  Step 4: Select a server type:")
    server_table = Table()
    server_table.add_column("ID", style="cyan", justify="center")
    server_table.add_column("Server", style="green")
    server_table.add_column("Description", style="yellow")
    
    for i, server in enumerate(ServerType, 1):
        if server == ServerType.VLLM:
            description = "Best for high-performance GPU inference"
        elif server == ServerType.OLLAMA:
            description = "Good balance of performance and ease of use"
        elif server == ServerType.LLAMACPP:
            description = "Best for CPU or lower-resource machines"
        server_table.add_row(str(i), server.value, description)
    
    console.print(server_table)
    
    server_choice = int(Prompt.ask("Enter your preferred server ID", default="1"))
    server = list(ServerType)[server_choice - 1] if 1 <= server_choice <= len(ServerType) else ServerType.OLLAMA
    
    # HuggingFace token is already collected in Step 1
    
    # Save configuration
    config = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
        except json.JSONDecodeError:
            config = {}
    
    # Update config with new values
    if 'hardware' not in config:
        config['hardware'] = {}
    
    config['hardware'].update({
        'use_gpu': use_gpu,
        'cpu_model': cpu_model,
        'cpu_cores': cpu_cores,
        'memory_gb': memory_gb,
        'gpu_vendor': gpu_vendor,
        'gpu_model': gpu_model,
        'gpu_memory': gpu_memory,
        'compute_backend': compute_backend,
        'os': os_name
    })
    
    if 'user' not in config:
        config['user'] = {}
    
    config['user'].update({
        'domain': custom_domain if domain == Domain.CUSTOM else domain.value,
    })
    
    if 'server' not in config:
        config['server'] = {}
    
    config['server'].update({
        'type': server.value
    })
    
    # Save HuggingFace credentials
    config['hugging_face'] = {
        'username': hf_username,
        'token': hf_token
    }
    
    
    # Setup environment based on server type
    if server == ServerType.OLLAMA:
        # Check for native Ollama installation first
        if is_ollama_natively_installed() and check_ollama_service_status():
            typer.echo("Native Ollama installation detected..")

            # Save native installation info to config
            if 'environment' not in config:
                config['environment'] = {}
            config['environment']['ollama_native'] = True
        else:
            if 'environment' not in config:
                config['environment'] = {}
            config['environment']['ollama_native'] = False
            
            # Proceed with Docker setup
            # Check if Docker is installed and running
            docker_running = False
            try:
                # Check if Docker is installed
                subprocess.run(["docker", "--version"], check=True, capture_output=True)
                
                # Try to get Docker info to check if it's running
                try:
                    subprocess.run(["docker", "info"], check=True, capture_output=True)
                    docker_running = True
                    typer.echo("✅ Docker is running.")
                except subprocess.CalledProcessError:
                    # Docker is installed but not running
                    typer.echo("⚠️  Docker is installed but not running. Trying to start Docker...")
                    docker_running = start_docker_engine(os_name)
                    
                    if not docker_running:
                        typer.echo("❌ Could not start Docker automatically.")
                        typer.echo("Please start Docker manually and run 'solo setup' again.")
                        return
            except FileNotFoundError:
                typer.echo("❌ Docker is not installed on your system.")
                typer.echo("Please install Docker Desktop from https://www.docker.com/products/docker-desktop/")
                typer.echo("After installation, run 'solo setup' again.")
                return
            
            # Pull the appropriate Docker image
            try:
                server_config = get_server_config('ollama')
                image = server_config.get('images', {}).get('default', "ollama/ollama")
                if gpu_vendor == "AMD" and use_gpu:
                    image = server_config.get('images', {}).get('amd', "ollama/ollama:rocm")
                
                typer.echo(f"\n📥 Pulling Docker image: {image}")
                subprocess.run(["docker", "pull", image], check=True)
                
            except subprocess.CalledProcessError as e:
                typer.echo(f"\n❌ Error setting up Docker environment: {e}", err=True)
                typer.echo("Please check your Docker configuration and run 'solo setup' again.")
                return
            except Exception as e:
                typer.echo(f"\n❌ An unexpected error occurred: {e}", err=True)
                return
            
    elif server == ServerType.VLLM:
        # Check if Docker is installed and running
        docker_running = False
        try:
            # Check if Docker is installed
            subprocess.run(["docker", "--version"], check=True, capture_output=True)
            
            # Try to get Docker info to check if it's running
            try:
                subprocess.run(["docker", "info"], check=True, capture_output=True)
                docker_running = True
                typer.echo("✅ Docker is running.")
            except subprocess.CalledProcessError:
                # Docker is installed but not running - try to start it
                typer.echo("⚠️  Docker is installed but not running. Trying to start Docker...")
                docker_running = start_docker_engine(os_name)
                
                if not docker_running:
                    typer.echo("❌ Could not start Docker automatically.")
                    typer.echo("Please start Docker manually and run 'solo setup' again.")
                    return
        except FileNotFoundError:
            typer.echo("❌ Docker is not installed on your system.")
            typer.echo("Please install Docker Desktop from https://www.docker.com/products/docker-desktop/")
            typer.echo("After installation, run 'solo setup' again.")
            return
        
        # Pull the appropriate Docker image
        try:
            server_config = get_server_config('vllm')
            if gpu_vendor == "NVIDIA" and use_gpu:
                image = server_config.get('images', {}).get('nvidia', "vllm/vllm-openai:latest")
            elif gpu_vendor == "AMD" and use_gpu:
                image = server_config.get('images', {}).get('amd', "rocm/vllm")
            elif cpu_model == "Apple":
                image = server_config.get('images', {}).get('apple', "getsolo/vllm-arm")
            else:
                image = server_config.get('images', {}).get('cpu', "getsolo/vllm-cpu")
            
            typer.echo(f"\n📥 Pulling Docker image: {image}")
            subprocess.run(["docker", "pull", image], check=True)
        
        except subprocess.CalledProcessError as e:
            typer.echo(f"\n❌ Error setting up Docker environment: {e}", err=True)
            typer.echo("Please check your Docker configuration and run 'solo setup' again.")
            return
        except Exception as e:
            typer.echo(f"\n❌ An unexpected error occurred: {e}", err=True)
            return
            
    
    elif server == ServerType.LLAMACPP:
        typer.echo("\n⚙️  Setting up llama.cpp environment...")
        # For llama.cpp, we don't need Docker, but we need to install the Python package
        try:
            import llama_cpp
        except ImportError:
            typer.echo("📥 Installing server package...")
            
            # Check if the user is using uv for package management
            is_uv_available = subprocess.run(["uv", "--version"], check=False, capture_output=True)
            if is_uv_available.returncode == 0:
                using_uv = Confirm.ask("Are you using uv for Python package management?", default=False)
            else:
                using_uv = False
            
            # Save package manager info to config
            if 'environment' not in config:
                config['environment'] = {}
            config['environment']['package_manager'] = 'uv' if using_uv else 'pip'
            
            # setup_llama_cpp_server for hardware-specific installation
            from solo.utils.llama_cpp_utils import setup_llama_cpp_server

            if setup_llama_cpp_server(use_gpu, gpu_vendor, os_name, using_uv):
                typer.echo("✅ Server package installed successfully with hardware optimizations")
            else:
                typer.echo("❌ Failed to install package. Please check your Python environment.")
                return

    # Create configuration directory if it doesn't exist
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

    # Save configuration to file
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)
    
    typer.echo(f"\nConfiguration saved to {CONFIG_PATH}")
    typer.echo("🎉 Solo CLI setup completed successfully!")
    typer.secho(f"Use 'solo serve -m model_name' to start serving your model.", fg=typer.colors.GREEN)
