import typer
import subprocess
import os
from huggingface_hub import HfApi

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
def merge(
    config_path: str,
    output_dir: str = "./merged_model",
    cuda: bool = False,
    allow_crimes: bool = False,
    upload: bool = False,
    hf_repo: str = "",
):
    """
    Merges models using MergeKit, supporting SLERP and gradient-based merging.
    """
    typer.echo(f"🚀 Running MergeKit with config: {config_path}")

    command = ["mergekit-yaml", config_path, output_dir]
    if cuda:
        command.append("--cuda")
    if allow_crimes:
        command.append("--allow-crimes")

    run_command(command)
    typer.echo(f"✅ Merging complete! Model saved at {output_dir}")

    # Upload to Hugging Face
    if upload:
        if not hf_repo:
            typer.echo("❌ Hugging Face repository required for upload.", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"📤 Uploading model to Hugging Face: {hf_repo}")
        api = HfApi()
        api.upload_folder(folder_path=output_dir, repo_id=hf_repo, repo_type="model")
        typer.echo(f"✅ Model uploaded to https://huggingface.co/{hf_repo}")


if __name__ == "__main__":
    app()
