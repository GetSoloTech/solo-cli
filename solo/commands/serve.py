import typer
import os
import json
import subprocess
from datetime import datetime

from enum import Enum
from typing import Optional
from solo.config import CONFIG_PATH
from solo.config.config_loader import get_server_config
from solo.utils.hardware import detect_hardware
from solo.utils.docker_utils import start_docker_engine
from solo.utils.hardware import is_ollama_natively_installed, check_ollama_service_status
from solo.utils.server_utils import (start_vllm_server, 
                                            start_ollama_server, 
                                            start_llama_cpp_server, 
                                            is_huggingface_repo, 
                                            pull_model_from_huggingface,
                                            pull_native_model_from_huggingface,
                                            pull_ollama_model,
                                            pull_native_ollama_model,
                                            start_ui)

class ServerType(str, Enum):
    OLLAMA = "ollama"
    VLLM = "vllm"
    LLAMACPP = "llama.cpp"

def serve(
    model: Optional[str] = typer.Option(None, "--model", "-m", help="""Model name or path. Can be:
    - HuggingFace repo ID (e.g., 'meta-llama/Llama-3.2-1B-Instruct')
    - Ollama model Registry (e.g., 'llama3.2')
    - Local path to a model file (e.g., '/path/to/model.gguf')
    If not specified, the default model from configuration will be used."""),
    server: Optional[str] = typer.Option(None, "--server", "-s", help="Server type (ollama, vllm, llama.cpp)"), 
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Port to run the server on"),
    ui: Optional[bool] = typer.Option(True, "--ui", help="Start the UI for the server")
):
    """Start a model server with the specified model.
    
    """
    
    from solo.state import state
    if state.get("non_interactive"):
        import sys
        if not sys.stdin.isatty():
            try:
                stdin_data = json.load(sys.stdin)
                model = stdin_data.get("model", model)
                server = stdin_data.get("server", server)
                port = stdin_data.get("port", port)
                ui = stdin_data.get("ui", ui)
            except Exception:
                pass

    # Check if config file exists
    if not os.path.exists(CONFIG_PATH):
        typer.echo("❌ Configuration file not found. Please run 'solo setup' first.", err=True)
        typer.echo("Run 'solo setup' to complete the Solo CLI setup and then try again.")
        raise typer.Exit(code=1)
    
    # Load configuration
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
    
    # Extract hardware info from config
    hardware_config = config.get('hardware', {})
    use_gpu = hardware_config.get('use_gpu', False)
    cpu_model = hardware_config.get('cpu_model')
    gpu_vendor = hardware_config.get('gpu_vendor')
    os_name = hardware_config.get('os')
    
    # If hardware info isn't in config, detect it
    if not cpu_model or not gpu_vendor or not os_name:
        cpu_model, _, _, gpu_vendor, _, _, _, os_name = detect_hardware()
    
    # Only enable GPU if configured and supported
    gpu_enabled = use_gpu and gpu_vendor in ["NVIDIA", "AMD", "Apple Silicon"]
    
    # Use server from config if not specified
    if not server:
        server = config.get('server', {}).get('type', ServerType.OLLAMA.value)
    else:
        # Normalize server name
        server = server.lower()
    
    # Validate server type
    if server not in [s.value for s in ServerType]:
        typer.echo(f"❌ Invalid server type: {server}. Choose from: {', '.join([s.value for s in ServerType])}", err=True)
        raise typer.Exit(code=1)
    
    # Get server configurations from YAML
    vllm_config = get_server_config('vllm')
    ollama_config = get_server_config('ollama')
    llama_cpp_config = get_server_config('llama_cpp')
    
    # Set default models based on server type
    if not model:
        if server == ServerType.VLLM.value:
            model = vllm_config.get('default_model', "meta-llama/Llama-3.2-1B-Instruct")
        elif server == ServerType.OLLAMA.value:
            model = ollama_config.get('default_model', "llama3.2")
        elif server == ServerType.LLAMACPP.value:
            model = llama_cpp_config.get('default_model', "bartowski/Llama-3.2-1B-Instruct-GGUF/llama-3.2-1B-Instruct-Q4_K_M.gguf")
    
    if not port:
        if server == ServerType.VLLM.value:
            port = vllm_config.get('default_port', 5070)
        elif server == ServerType.OLLAMA.value:
            # Check if using native Ollama to determine the correct port
            use_native = False
            try:
                if os.path.exists(CONFIG_PATH):
                    with open(CONFIG_PATH, 'r') as f:
                        config_data = json.load(f)
                        use_native = config_data.get('environment', {}).get('ollama_native', False)
            except:
                pass
            
            # Check if native Ollama is available and running
            if (use_native or is_ollama_natively_installed()) and check_ollama_service_status():
                use_native = True
                port = ollama_config.get('native_port', 11434)  # Use native Ollama port
            else:
                port = ollama_config.get('default_port', 5070)  # Use Docker port
        elif server == ServerType.LLAMACPP.value:
            port = llama_cpp_config.get('default_port', 5070)
    
    # Start the appropriate server
    typer.echo(f"Starting Solo CLI...")
    success = False
    original_model_name = model

    # Check Docker is installed and running for Docker-based servers
    if server in [ServerType.VLLM.value]:
        # Check if Docker is installed
        try:
            subprocess.run(["docker", "--version"], check=True, capture_output=True)
        except FileNotFoundError:
            typer.echo("❌ Docker is not installed on your system.", err=True)
            typer.echo("Please install Docker Desktop from https://www.docker.com/products/docker-desktop/")
            typer.echo("After installation, run 'solo setup'.")
            raise typer.Exit(code=1)
        
        # Check if Docker is running
        docker_running = False
        try:
            subprocess.run(["docker", "info"], check=True, capture_output=True)
            docker_running = True
        except subprocess.CalledProcessError:
            docker_running = False
            typer.echo("⚠️  Docker is installed but not running. Trying to start Docker...")
            docker_running = start_docker_engine(os_name)
            
            if not docker_running:
                typer.echo("❌ Could not start Docker automatically.", err=True)
                typer.echo("Please start Docker manually and run 'solo serve' again.")
                raise typer.Exit(code=1)
            
        # Start vLLM server
        try:
            success = start_vllm_server(gpu_enabled, cpu_model, gpu_vendor, os_name, port, model)
            # Display container logs command
            if success:
                typer.echo(f"Use 'docker logs -f {vllm_config.get('container_name', 'solo-vllm')}' to view the logs.")
        except Exception as e:
            typer.echo(f"❌ Failed to start Solo CLI: {e}", err=True)
            raise typer.Exit(code=1)
    
    # For Ollama, check if we need Docker or can use native installation
    elif server == ServerType.OLLAMA.value:
        # Check if native Ollama is configured and running
        use_native = False
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r') as f:
                    config_data = json.load(f)
                    use_native = config_data.get('environment', {}).get('ollama_native', False)
        except:
            pass
        
        # Check if native Ollama is available and running
        if (use_native or is_ollama_natively_installed()) and check_ollama_service_status():
            use_native = True
            # Start native Ollama server
            if not start_ollama_server(gpu_enabled, gpu_vendor, port):
                typer.echo("❌ Failed to start Solo CLI!", err=True)
                raise typer.Exit(code=1)
            
            # Pull the model if not already available
            try:
                # Check if this is a HuggingFace model
                if is_huggingface_repo(model):
                    # Pull from HuggingFace using native Ollama
                    model = pull_native_model_from_huggingface(model)
                else:
                    # Pull or use existing Ollama model using native Ollama
                    model = pull_native_ollama_model(model)
                            
                success = True
            except subprocess.CalledProcessError as e:
                typer.echo(f"❌ Failed to pull model: {e}", err=True)
                raise typer.Exit(code=1)
            
        elif is_ollama_natively_installed():
            # Native Ollama is installed but not running - fall back to Docker
            use_native = False
        
        if not use_native:
            # Check if Docker is installed
            try:
                subprocess.run(["docker", "--version"], check=True, capture_output=True)
            except FileNotFoundError:
                typer.echo("❌ Docker is not installed on your system.", err=True)
                typer.echo("Please install Docker Desktop from https://www.docker.com/products/docker-desktop/")
                typer.echo("After installation, run 'solo setup'.")
                raise typer.Exit(code=1)
            
            # Check if Docker is running
            docker_running = False
            try:
                subprocess.run(["docker", "info"], check=True, capture_output=True)
                docker_running = True
            except subprocess.CalledProcessError:
                docker_running = False
                typer.echo("⚠️  Docker is installed but not running. Trying to start Docker...")
                docker_running = start_docker_engine(os_name)
                
                if not docker_running:
                    typer.echo("❌ Could not start Docker automatically.", err=True)
                    typer.echo("Please start Docker manually and run 'solo serve' again.")
                    raise typer.Exit(code=1)
            
            # Start Docker-based Ollama server
            if not start_ollama_server(gpu_enabled, gpu_vendor, port):
                typer.echo("❌ Failed to start Solo CLI!", err=True)
                raise typer.Exit(code=1)
            
            # Pull the model if not already available
            try:
                # Check if model exists
                container_name = ollama_config.get('container_name', 'solo-ollama')
                
                # Check if this is a HuggingFace model
                if is_huggingface_repo(model):
                    # Pull from HuggingFace
                    model = pull_model_from_huggingface(container_name, model)
                else:
                    # Pull or use existing Ollama model
                    model = pull_ollama_model(container_name, model)
                            
                success = True
            except subprocess.CalledProcessError as e:
                typer.echo(f"❌ Failed to pull model: {e}", err=True)
                raise typer.Exit(code=1)
            
    elif server == ServerType.LLAMACPP.value:
        # Start llama.cpp server with the specified model
        success = start_llama_cpp_server(os_name, model_path=model, port=port)
        if not success:
            typer.echo("❌ Failed to start Solo CLI", err=True)
            raise typer.Exit(code=1)
    
    # Display server information in the requested format
    if success:
        # Get formatted model name for display
        display_model = original_model_name
        if is_huggingface_repo(original_model_name):
            # For HF models, get the repository name for display
            display_model = original_model_name.split('/')[-1] if '/' in original_model_name else original_model_name
        
        # Prepare full_model_name for storage
        full_model_name = original_model_name
        if is_huggingface_repo(original_model_name):
            # For HuggingFace repositories, add hf.co/ prefix if not already present
            if not original_model_name.startswith("hf://") and not original_model_name.startswith("hf.co/"):
                full_model_name = f"hf.co/{original_model_name}"
        
        # Save model information to config file
        # Update config with active model information
        config['active_model'] = {
            'server': server,
            'name': display_model,
            'full_model_name': full_model_name,  # Save the complete model name with hf.co/ prefix for HF repos
            'port': port,  # Save the server port for the UI to use
            'last_used': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Make sure server section exists
        if 'server' not in config:
            config['server'] = {}
            
        # Update server type in config
        config['server']['type'] = server
        
        # Save the specific server config with port
        if server not in config['server']:
            config['server'][server] = {}
            
        config['server'][server]['default_port'] = port
        
        # Save updated config
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=4)
        
        # Print server information
        typer.echo("✅ Solo CLI is running")
        typer.secho(f"Model  - {display_model}", fg=typer.colors.BRIGHT_CYAN, bold=True)
        typer.secho(f"Access Server at - http://localhost:{port}", fg=typer.colors.BRIGHT_CYAN, bold=True)
        
        # Get container name based on server type
        if server == ServerType.VLLM.value:
            container_name = vllm_config.get('container_name', 'solo-vllm')
        elif server == ServerType.OLLAMA.value:
            container_name = ollama_config.get('container_name', 'solo-ollama')
        else:  # llama.cpp doesn't have a container
            container_name = None
            
        # Start UI container if enabled
#        if ui:
#            typer.echo("\nStarting Solo UI...")
#            ui_port = 9000  # Default UI port
            
            # Start the UI container
#            ui_success = start_ui(server, container_name=container_name)
            
#            if ui_success:
#                typer.echo("✅ Solo UI is running")
#                typer.secho(f"Access UI at - http://localhost:{ui_port}", fg=typer.colors.BRIGHT_CYAN, bold=True)
#            else:
#                typer.echo("⚠️ Failed to start UI automatically.")
#                typer.echo(f"You can manually access the server at http://localhost:{port}")
#                typer.echo(f"Or use 'solo test' to test the server.")
#        else:
#            typer.secho(f"UI not started. Use 'solo test' to test the server or '--ui' flag to start the UI.", fg=typer.colors.BRIGHT_MAGENTA)
