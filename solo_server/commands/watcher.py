import typer
import subprocess
import torch
import torchvision.models as models
import weightwatcher as ww
import pandas as pd

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
def install_weightwatcher():
    """
    Installs WeightWatcher. Tries official PyPI first, then TestPyPI if it fails.
    """
    typer.echo("📦 Installing WeightWatcher...")

    command = ["pip", "install", "weightwatcher"]
    try:
        run_command(command)
        typer.echo("✅ WeightWatcher installed successfully!")
    except:
        typer.echo("⚠️ Standard installation failed. Trying TestPyPI...")
        command = [
            "python3", "-m", "pip", "install",
            "--index-url", "https://test.pypi.org/simple/",
            "--extra-index-url", "https://pypi.org/simple",
            "weightwatcher"
        ]
        run_command(command)
        typer.echo("✅ WeightWatcher installed from TestPyPI!")


@app.command()
def analyze(
    model_name: str = typer.Argument(..., help="Torchvision model name (e.g., vgg19_bn, resnet50)"),
    save_results: bool = typer.Option(False, help="Save analysis results as CSV")
):
    """
    Analyzes a model using WeightWatcher and prints generalization metrics.
    """
    typer.echo(f"🔍 Analyzing model: {model_name}")

    # Load the model from torchvision
    try:
        model = getattr(models, model_name)(pretrained=True)
    except AttributeError:
        typer.echo(f"❌ Error: Model '{model_name}' not found in torchvision.models", err=True)
        raise typer.Exit(code=1)

    # Run WeightWatcher analysis
    watcher = ww.WeightWatcher(model=model)
    details = watcher.analyze()
    summary = watcher.get_summary(details)

    typer.echo("📊 Model Analysis Summary:")
    typer.echo(summary)

    if save_results:
        details_df = pd.DataFrame(details)
        csv_filename = f"{model_name}_analysis.csv"
        details_df.to_csv(csv_filename, index=False)
        typer.echo(f"✅ Analysis results saved to {csv_filename}")


if __name__ == "__main__":
    app()
