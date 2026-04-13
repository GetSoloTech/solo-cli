import typer
import subprocess
import os
from datasets import load_dataset
from gptqmodel import GPTQModel, QuantizeConfig

app = typer.Typer()

def run_command(command):
    """
    Runs a shell command and prints output.
    """
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        typer.echo(result.stdout)
    except subprocess.CalledProcessError as e:
        typer.echo(f"❌ Command failed: {e.stderr}", err=True)


@app.command()
def install_gptqmodel():
    """
    Installs GPTQModel. Tries official PyPI first, then from source if necessary.
    """
    typer.echo("📦 Installing GPTQModel...")

    command = ["pip", "install", "-v", "--no-build-isolation", "gptqmodel"]
    try:
        run_command(command)
        typer.echo("✅ GPTQModel installed successfully!")
    except:
        typer.echo("⚠️ Standard installation failed. Trying source installation...")

        command = [
            "git", "clone", "https://github.com/ModelCloud/GPTQModel.git", "GPTQModel"
        ]
        run_command(command)

        os.chdir("GPTQModel")

        command = ["pip", "install", "-v", "--no-build-isolation", "."]
        run_command(command)

        typer.echo("✅ GPTQModel installed from source!")


@app.command()
def quantize(
    model_id: str = typer.Argument(..., help="Hugging Face model ID to quantize"),
    output_dir: str = typer.Option("./quantized_model", help="Directory to save quantized model"),
    dataset: str = typer.Option("allenai/c4", help="Dataset for calibration"),
    dataset_file: str = typer.Option("en/c4-train.00001-of-01024.json.gz", help="Calibration file"),
    num_samples: int = typer.Option(1024, help="Number of calibration samples"),
    bits: int = typer.Option(4, help="Quantization bits"),
    group_size: int = typer.Option(128, help="Quantization group size"),
    batch_size: int = typer.Option(2, help="Batch size for quantization"),
):
    """
    Quantizes a model using GPTQModel and saves the output.
    """
    typer.echo(f"🔧 Quantizing model: {model_id} with {bits}-bit precision...")

    # Load calibration dataset
    calibration_dataset = load_dataset(dataset, data_files=dataset_file, split="train").select(range(num_samples))["text"]

    # Define quantization config
    quant_config = QuantizeConfig(bits=bits, group_size=group_size)

    # Load model and perform quantization
    model = GPTQModel.load(model_id, quant_config)
    model.quantize(calibration_dataset, batch_size=batch_size)

    # Save quantized model
    model.save(output_dir)
    typer.echo(f"✅ Quantized model saved to {output_dir}")

    # Test post-quantization inference
    test_prompt = "Uncovering deep insights begins with"
    result = model.generate(test_prompt)[0]
    typer.echo(f"📜 Sample Output: {model.tokenizer.decode(result)}")


@app.command()
def serve_quantized_model(
    model_path: str = typer.Argument(..., help="Path to the quantized model"),
    host: str = typer.Option("0.0.0.0", help="Host IP address"),
    port: int = typer.Option(12345, help="Port for serving model"),
):
    """
    Serves a quantized model using OpenAI-compatible API.
    """
    typer.echo(f"🚀 Serving quantized model at {host}:{port}")
    
    model = GPTQModel.load(model_path)
    model.serve(host=host, port=str(port))
    typer.echo(f"✅ Model API is running at http://{host}:{port}")


if __name__ == "__main__":
    app()
