import typer
import os
import json
import subprocess
import glob
import time
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from datetime import datetime

from solo.config import CONFIG_PATH
from solo.config.config_loader import get_server_config
from solo.utils.hardware import is_ollama_natively_installed, check_ollama_service_status

console = Console()

from solo.state import state

def list():
    """
    List all downloaded models available in HuggingFace cache and Ollama.
    """
    is_json = state.get("output_format", "text") == "json"
    
    if not is_json:
        typer.echo("\n🔍 Scanning for available models...")
    
    # Initialize tables
    hf_table = Table(title="HuggingFace Models")
    hf_table.add_column("MODEL", style="cyan")
    hf_table.add_column("SIZE", style="green")
    hf_table.add_column("LAST MODIFIED", style="yellow")
    
    ollama_table = Table(title="Ollama Models")
    ollama_table.add_column("NAME", style="cyan")
    ollama_table.add_column("SIZE", style="green")
    ollama_table.add_column("MODIFIED", style="yellow")
    ollama_table.add_column("TAGS", style="magenta")
    
    hf_models_list = []
    ollama_models_list = []

    # Check for HuggingFace models in cache
    hf_models_found = False
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    
    if os.path.exists(cache_dir):
        # Look for models (typically in model directories containing .bin, .gguf, .safetensors files)
        model_extensions = ['.bin', '.gguf', '.safetensors']
        
        # Track models to avoid duplicates
        processed_models = set()
        
        # Scan HuggingFace cache directory
        for root, dirs, files in os.walk(cache_dir):
            model_files = []
            
            # Find model files with specific extensions
            for ext in model_extensions:
                model_files.extend(glob.glob(os.path.join(root, f"*{ext}")))
            
            if model_files:
                # Try to extract model name from path
                model_name = None
                model_path = Path(root)
                
                # Extract model name from models--org--name pattern
                path_str = str(model_path)
                if "models--" in path_str:
                    # Use more reliable extraction based on path components
                    path_parts = path_str.split(os.sep)
                    for part in path_parts:
                        if part.startswith("models--"):
                            # Convert "models--org--name" to "org/name"
                            model_parts = part.split("--")
                            if len(model_parts) >= 3:
                                model_name = f"{model_parts[1]}/{model_parts[2]}"
                                break
                
                # Skip if we couldn't determine model name
                if not model_name:
                    continue
                
                # Skip if we've already processed this model (avoid duplicates)
                if model_name in processed_models:
                    continue
                
                processed_models.add(model_name)
                
                # Find the largest model file (likely the main model)
                if model_files:
                    # Pick the largest relevant file
                    largest_file = max(model_files, key=os.path.getsize)
                    size = os.path.getsize(largest_file)
                    size_str = _format_size(size)
                    mod_time = os.path.getmtime(largest_file)
                    mod_time_str = datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M")
                    
                    # Add to table with only model name, size, and modification date
                    hf_table.add_row(model_name, size_str, mod_time_str)
                    hf_models_list.append({"model": model_name, "size": size_str, "modified": mod_time_str})
                    hf_models_found = True
    
    # Check for Ollama models
    ollama_models_found = False
    
    # Check if native Ollama is available and running
    use_native = is_ollama_natively_installed() and check_ollama_service_status()
    
    if use_native:
        # Use native Ollama
        try:
            models_output = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                check=True
            ).stdout.strip()
            
            if models_output:
                # Parse the output - typical format is:
                # NAME                    ID              SIZE    MODIFIED
                # llama3.2                7e0c91e2d847    5.8 GB  6 days ago
                lines = models_output.split('\n')
                if len(lines) > 1:  # Skip header
                    for line in lines[1:]:
                        parts = line.split()
                        if len(parts) >= 4:
                            # Extract name (first part)
                            name = parts[0]
                            
                            # Extract model_id (second part)
                            model_id = parts[1]
                            
                            # Extract size (considering it may be "807 MB" or "1.1 GB")
                            # Look for size unit (MB, GB, etc.) to identify the size parts
                            size_idx = -1
                            for i, part in enumerate(parts[2:], 2):
                                if part.upper() in ['B', 'KB', 'MB', 'GB', 'TB']:
                                    size_idx = i
                                    break
                            
                            # If size unit found, combine with the value before it
                            if size_idx > 2:  # Found size unit after the value
                                size = f"{parts[size_idx-1]} {parts[size_idx]}"
                                # Modified starts after the size parts
                                modified = ' '.join(parts[size_idx+1:])
                            else:
                                # Default fallback if parsing fails
                                size = parts[2]
                                modified = ' '.join(parts[3:])
                            
                            # Check for tags
                            tags = ""
                            if ":" in name:
                                name, tags = name.split(":", 1)
                            ollama_table.add_row(name, size, modified, tags)
                            ollama_models_list.append({"name": name, "size": size, "modified": modified, "tags": tags})
                            ollama_models_found = True
        except subprocess.CalledProcessError as e:
            if not is_json:
                typer.echo(f"⚠️  Error checking native Ollama models: {e}", err=True)
        except FileNotFoundError:
            if not is_json:
                typer.echo("⚠️  Native Ollama not found or not accessible", err=True)
    
    else:
        ollama_container = get_server_config('ollama').get('container_name', 'solo-ollama')
        
        try:
            # Check if Docker is running
            docker_running = False
            try:
                # Capture Docker info and suppress output
                subprocess.run(["docker", "info"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                docker_running = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
            
            if docker_running:
                # Check if Ollama container exists (running or stopped)
                container_exists = subprocess.run(
                    ["docker", "ps", "-a", "-q", "-f", f"name={ollama_container}"],
                    capture_output=True,
                    text=True
                ).stdout.strip()
                
                # Variable to track if we started the container and need to stop it
                container_started = False
                
                if container_exists:
                    # Check if container is running
                    container_running = subprocess.run(
                        ["docker", "ps", "-q", "-f", f"name={ollama_container}"],
                        capture_output=True,
                        text=True
                    ).stdout.strip()
                    
                    if not container_running:
                        # Container exists but is not running - start it
                        try:
                            # Start the container
                            subprocess.run(
                                ["docker", "start", ollama_container],
                                check=True,
                                stdout=subprocess.DEVNULL,  # Suppress stdout
                                stderr=subprocess.PIPE     # Only capture stderr for errors
                            )
                            container_started = True
                            
                            # Wait for container to be ready (up to 10 seconds)
                            max_wait = 10
                            ready = False
                            for _ in range(max_wait):
                                try:
                                    # Try to run a simple command to check if container is ready
                                    subprocess.run(
                                        ["docker", "exec", ollama_container, "ollama", "list"],
                                        check=True,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE
                                    )
                                    ready = True
                                    break
                                except subprocess.CalledProcessError:
                                    # Container not ready yet
                                    time.sleep(1)
                            
                            if not ready:
                                typer.echo("⚠️  container started but not ready in time")
                                if container_started:
                                    subprocess.run(["docker", "stop", ollama_container], check=False, 
                                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                                return
                            
                        except subprocess.CalledProcessError as e:
                            typer.echo(f"❌ Failed to start Ollama container: {e}", err=True)
                            return
                    
                    # Now get list of models from Ollama 
                    try:
                        models_output = subprocess.run(
                            ["docker", "exec", ollama_container, "ollama", "list"],
                            capture_output=True,
                            text=True,
                            check=True
                        ).stdout.strip()
                        
                        if models_output:
                            # Parse the output - typical format is:
                            # NAME                    ID              SIZE    MODIFIED
                            # llama3.2                7e0c91e2d847    5.8 GB  6 days ago
                            lines = models_output.split('\n')
                            if len(lines) > 1:  # Skip header
                                for line in lines[1:]:
                                    parts = line.split()
                                    if len(parts) >= 4:
                                        # Extract name (first part)
                                        name = parts[0]
                                        
                                        # Extract model_id (second part)
                                        model_id = parts[1]
                                        
                                        # Extract size (considering it may be "807 MB" or "1.1 GB")
                                        # Look for size unit (MB, GB, etc.) to identify the size parts
                                        size_idx = -1
                                        for i, part in enumerate(parts[2:], 2):
                                            if part.upper() in ['B', 'KB', 'MB', 'GB', 'TB']:
                                                size_idx = i
                                                break
                                        
                                        # If size unit found, combine with the value before it
                                        if size_idx > 2:  # Found size unit after the value
                                            size = f"{parts[size_idx-1]} {parts[size_idx]}"
                                            # Modified starts after the size parts
                                            modified = ' '.join(parts[size_idx+1:])
                                        else:
                                            # Default fallback if parsing fails
                                            size = parts[2]
                                            modified = ' '.join(parts[3:])
                                        
                                        # Check for tags
                                        tags = ""
                                        if ":" in name:
                                            name, tags = name.split(":", 1)
                                        ollama_table.add_row(name, size, modified, tags)
                                        ollama_models_list.append({"name": name, "size": size, "modified": modified, "tags": tags})
                                        ollama_models_found = True
                    finally:
                        # Stop the container if we started it
                        if container_started:
                            subprocess.run(["docker", "stop", ollama_container], check=False,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except Exception as e:
            typer.echo(f"⚠️  Error checking Ollama models: {e}", err=True)
            # Ensure container is stopped if we started it and an error occurred
            if docker_running and container_exists and container_started:
                subprocess.run(["docker", "stop", ollama_container], check=False,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    
    # Display results
    if is_json:
        print(json.dumps({"huggingface_models": hf_models_list, "ollama_models": ollama_models_list}, indent=2))
        return

    if hf_models_found:
        console.print(hf_table)
    else:
        typer.echo("No HuggingFace models found in cache.")
    
    if ollama_models_found:
        console.print(ollama_table)
    
    # Show hints if no models found
    if not hf_models_found and not ollama_models_found:
        typer.echo("\nℹ️  You can download models using:")
        typer.echo("  • solo download -m <huggingface-model-id>  : Download from HuggingFace")
        typer.echo("  • solo serve -s ollama -m <model-name>     : Download and serve with Ollama")

def _format_size(size_bytes):
    """Format file size in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024 or unit == 'TB':
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
