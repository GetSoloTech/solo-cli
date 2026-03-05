import typer
import subprocess
import os
import json
import socket
import psutil
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from solo.config import CONFIG_PATH
from solo.config.config_loader import get_server_config
from solo.utils.llama_cpp_utils import find_process_by_port
from solo.utils.hardware import is_ollama_natively_installed, check_ollama_service_status

console = Console()

def status():
    """Check running models, system status, and configuration."""
    
    # Check if config file exists
    if not os.path.exists(CONFIG_PATH):
        typer.echo("❌ Configuration file not found. Please run 'solo setup' first.")
        return
    
    # Load configuration
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
    
    # Display configuration in one consolidated table
    typer.echo("\n📊 Solo Configuration:")
    
    # Create a single configuration table
    config_table = Table(title="Configuration")
    config_table.add_column("CATEGORY", style="cyan")
    config_table.add_column("PROPERTY", style="blue")
    config_table.add_column("VALUE", style="green")
    
    # Track current category to add spacing
    current_category = None
    
    # Hardware Configuration
    hardware_config = config.get('hardware', {})
    if hardware_config:
        current_category = "Hardware"
        config_table.add_row("Hardware", "CPU Model", hardware_config.get('cpu_model', 'Not available'))
        config_table.add_row("Hardware", "CPU Cores", str(hardware_config.get('cpu_cores', 'Not available')))
        config_table.add_row("Hardware", "Memory (GB)", str(hardware_config.get('memory_gb', 'Not available')))
        config_table.add_row("Hardware", "GPU Vendor", hardware_config.get('gpu_vendor', 'None'))
        config_table.add_row("Hardware", "GPU Model", hardware_config.get('gpu_model', 'None'))
        config_table.add_row("Hardware", "GPU Memory", str(hardware_config.get('gpu_memory', 'Not available')))
        config_table.add_row("Hardware", "GPU Enabled", "Yes" if hardware_config.get('use_gpu', False) else "No")
        config_table.add_row("Hardware", "Operating System", hardware_config.get('os', 'Not available'))
    
    # Server Configuration - add empty row for spacing
    config_table.add_row("", "", "")
    current_category = "Server"
    
    server_type = config.get('server', {}).get('type', 'Not set')
    server_config = get_server_config(server_type)
    
    config_table.add_row("Server", "Default Server", server_type)
    config_table.add_row("Server", "Default Port", str(server_config.get('default_port', '5070')))
    config_table.add_row("Server", "Default Model", server_config.get('default_model', 'Not set'))
    
    # User Info - add empty row for spacing
    config_table.add_row("", "", "")
    current_category = "User"
    
    user_config = config.get('user', {})
    if user_config:
        config_table.add_row("User", "Domain", user_config.get('domain', 'Not set'))
        config_table.add_row("User", "Role", user_config.get('role', 'Not set'))
    
    # Remove active model section from config table
    console.print(config_table)
    
    # Check for running services
    running_services = []
    
    # Check for native Ollama first
    native_ollama_running = False
    if is_ollama_natively_installed() and check_ollama_service_status():
        native_ollama_running = True
        
        # Get model name from config if available
        model_name = "Unknown"
        if config.get('active_model', {}).get('server') == 'ollama':
            model_name = config.get('active_model', {}).get('name', model_name)
        
        # Get native Ollama port from config
        ollama_config = get_server_config('ollama')
        native_port = ollama_config.get('native_port', 11434)
        
        running_services.append([
            "Native Ollama",
            model_name,
            f"http://localhost:{native_port}",
            "Running"
        ])
    
    # Check for Docker
    docker_installed = False
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
        docker_installed = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    # Check for running containers if Docker is installed
    containers = []
    if docker_installed:
        try:
            # Check if docker is running
            docker_running = False
            try:
                subprocess.run(["docker", "ps"], capture_output=True, check=True)
                docker_running = True
            except subprocess.CalledProcessError:
                pass
            
            if docker_running:
                # Check for running solo containers
                container_result = subprocess.run(["docker", "ps", "-f", "name=solo*", "--format", "{{json .}}"],
                                            capture_output=True, text=True, check=True)
                
                if container_result.stdout.strip():
                    for line in container_result.stdout.strip().split('\n'):
                        container = json.loads(line)
                        containers.append({
                            'name': container['Names'],
                            'status': container['Status'],
                            'ports': container['Ports']
                        })
        except Exception as e:
            pass
    
    # Check for llama.cpp server
    try:
        # Check default port 5070
        default_port = 5070
        is_port_used = False
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                result = s.connect_ex(('127.0.0.1', default_port))
                is_port_used = (result == 0)
        except:
            pass
        
        if is_port_used:
            process = find_process_by_port(default_port)
            if process:
                cmd_line = " ".join(process.cmdline()) if hasattr(process, 'cmdline') else ""
                # Check if this is a llama.cpp server
                if "llama_cpp.server" in cmd_line:
                    # Get model name from command line
                    model_name = "Unknown"
                    try:
                        cmd_parts = cmd_line.split()
                        for i, part in enumerate(cmd_parts):
                            if part == "--model" and i+1 < len(cmd_parts):
                                model_path = cmd_parts[i+1]
                                model_name = os.path.basename(model_path)
                    except:
                        pass
                    
                    # Use model name from config if available
                    if config.get('active_model', {}).get('server') == 'llama.cpp':
                        model_name = config.get('active_model', {}).get('name', model_name)
                    
                    running_services.append([
                        "llama.cpp",
                        model_name,
                        f"http://localhost:{default_port}",
                        "Running"
                    ])
                # Docker containers would be checked separately
                elif not any("solo-vllm" in container['name'] or "solo-ollama" in container['name'] for container in containers):
                    # Unknown service on this port
                    running_services.append([
                        "Unknown Service",
                        "N/A",
                        f"http://localhost:{default_port}",
                        "Port in use"
                    ])
    except Exception as e:
        pass
    
    # Check for vLLM and Ollama in containers (only if native Ollama is not running)
    for container in containers:
        # vLLM container
        if "solo-vllm" in container['name']:
            # Extract port from the ports string correctly
            port = "5070"  # Default
            ports_str = container['ports']
            
            # Parse port mapping properly
            # Format can be like "0.0.0.0:5070->8000/tcp"
            if ports_str and "->" in ports_str:
                try:
                    # Extract the external port (before ->)
                    port_part = ports_str.split("->")[0]
                    if ":" in port_part:
                        port = port_part.split(":")[1]
                except:
                    pass
            
            # Get model name from config if available
            model_name = "Unknown"
            if config.get('active_model', {}).get('server') == 'vllm':
                model_name = config.get('active_model', {}).get('name', model_name)
            
            running_services.append([
                "vLLM",
                model_name,
                f"http://localhost:{port}",
                "Running"
            ])
        
        # Ollama container (only show if native Ollama is not running)
        elif "solo-ollama" in container['name'] and not native_ollama_running:
            # Extract port from the ports string correctly
            port = "5070"  # Default
            ports_str = container['ports']
            
            # Parse port mapping properly
            # Format can be like "0.0.0.0:5070->11434/tcp"
            if ports_str and "->" in ports_str:
                try:
                    # Extract the external port (before ->)
                    port_part = ports_str.split("->")[0]
                    if ":" in port_part:
                        port = port_part.split(":")[1]
                except:
                    pass
            
            # Get model name from config if available
            model_name = "Unknown"
            if config.get('active_model', {}).get('server') == 'ollama':
                model_name = config.get('active_model', {}).get('name', model_name)
            
            running_services.append([
                "Docker Ollama",
                model_name,
                f"http://localhost:{port}",
                "Running"
            ])
    
    # Display running services
    if running_services:
        typer.echo("\n🚀 Running Services:")
        services_table = Table(title="Running Services")
        services_table.add_column("SERVICE", style="cyan")
        services_table.add_column("MODEL", style="magenta")
        services_table.add_column("URL", style="yellow")
        services_table.add_column("STATUS", style="green")
        for service in running_services:
            services_table.add_row(*service)
        console.print(services_table)
    else:
        typer.echo("\n⚠️  No services running.")

    console.print(
        "\nTo check a model's training status, run [bold]solo status org/model_name[/bold].",
        style="dim",
    )
